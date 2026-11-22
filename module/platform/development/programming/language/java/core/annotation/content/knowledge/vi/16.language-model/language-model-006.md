# Elements và Types khi kiểm tra tên, kiểu và quan hệ kiểu trong Java

Trong **annotation processor** và các công cụ phân tích mã Java khi biên dịch, hai interface trung tâm là **`javax.lang.model.util.Elements`** và **`javax.lang.model.util.Types`**. Chúng giúp xác định một khai báo có tên gì, thuộc loại nào, có thành viên nào, hay một kiểu có phải subtype hoặc gán được cho kiểu khác không. Những câu hỏi đó nên được trả lời bằng **compiler language model**, không phải cố nạp source đang biên dịch bằng `Class.forName(...)`.

- **`Elements`** thao tác với **khai báo** (`Element`): package, class, interface, field, method, constructor, parameter, type parameter; hỗ trợ lookup, members, override, hiding và annotation mirrors.
- **`Types`** thao tác với **kiểu** (`TypeMirror`): same type, subtype, assignment compatibility, generic instantiation, erasure, type substitutions, boxing/unboxing và wildcard types.
- Cả hai được cung cấp bởi `ProcessingEnvironment` trong lúc `javac` chạy processor.

~~~java
Elements elements = processingEnv.getElementUtils();
Types types = processingEnv.getTypeUtils();
~~~

Đoạn trên được viết **bên trong annotation processor đã khởi tạo**, không phải một chương trình có `main`. Mục 7 cung cấp ví dụ gồm hai file Java có thể biên dịch/chạy với `--release 17`.

## 1. Khai báo (Element) khác kiểu (TypeMirror) như thế nào?

Xét:

~~~java
class Base<T> {
    T value;
}

class Derived extends Base<String> {}
~~~

Có hai câu hỏi rất khác nhau:

1. **`Base` được khai báo ở đâu, tên đơn và tên đầy đủ là gì?** Đối tượng phù hợp là `TypeElement` của `Base`.
2. **`Derived` có phải subtype của `Base<String>` không?** Đối tượng cần so sánh là các `TypeMirror` biểu diễn **kiểu**, trong đó `Base<String>` có dạng `DeclaredType`.

Field `Base.value` là `VariableElement`. Ở chính lớp `Base<T>`, kiểu field được biểu diễn là `T`; khi tham chiếu field đó trong `Derived extends Base<String>`, kiểu thích hợp trở thành `String`. `Elements` tìm ra **khai báo field**, còn `Types.asMemberOf` suy ra **kiểu của field trong ngữ cảnh khác**.

| Đối tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Element` | Một khai báo compiler biết | `Base`, `value`, `get()` |
| `TypeElement` | Khai báo class/interface/annotation/enum/record | `demo.Derived` |
| `VariableElement` | Khai báo field hoặc parameter | `value` |
| `ExecutableElement` | Khai báo method hoặc constructor | `get()` |
| `PackageElement` | Khai báo package | `demo` |
| `TypeMirror` | Một kiểu Java trong hệ thống type | `String`, `List<String>` |
| `DeclaredType` | Kiểu tham chiếu khai báo, có thể mang generic arguments | `Base<String>` |
| `Elements` | Các thao tác trên elements/symbols | `getTypeElement`, `getAllMembers` |
| `Types` | Các thao tác trên type mirrors | `isSubtype`, `isAssignable` |

**Không thể thay `TypeMirror` bằng tên chuỗi đơn thuần.** Hai class có cùng simple name vẫn có thể khác qualified name. Ngược lại, kiểu có generic instantiation và thông tin subtype mà tên khai báo một mình không đủ biểu diễn.

## 2. Lấy Elements và Types đúng vòng đời xử lý

Processor thường kế thừa `javax.annotation.processing.AbstractProcessor` và ghi đè:

~~~java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    Elements elements = processingEnv.getElementUtils();
    Types types = processingEnv.getTypeUtils();
    // Phân tích declarations/types ở compilation round hiện tại.
    return false;
}
~~~

Đây là **đoạn minh họa**, giả định có các import cần thiết và nằm trong một subclass `AbstractProcessor`. Phần code hoàn chỉnh ở mục 7.

- `processingEnv` do compiler cấp khi processor khởi tạo; không tạo thủ công `new Elements()` hoặc `new Types()` vì chúng là interfaces.
- `RoundEnvironment` cung cấp elements thuộc vòng xử lý hiện tại, bao gồm `getElementsAnnotatedWith(...)`.
- Annotation processing có thể gồm **nhiều round** nếu processor sinh thêm source; `roundEnv.processingOver()` cho biết round kết thúc.
- Elements và TypeMirrors thuộc **compilation environment**, không phải các `Class`/`Method` runtime có thể giữ tùy ý sang lần chạy khác.

Các package chuẩn vẫn là **`javax.lang.model.element`**, **`javax.lang.model.type`**, **`javax.lang.model.util`** và **`javax.annotation.processing`**. Đừng đổi thành tên package `jakarta.lang.model` chỉ vì các framework khác đã chuyển sang Jakarta.

## 3. Dùng Elements để kiểm tra tên và members

### 3.1. Tra cứu bằng tên chuẩn

~~~java
TypeElement type = elements.getTypeElement("demo.Derived");
if (type == null) {
    // Chưa resolve được type với tên này trong compilation environment.
}
~~~

`Elements.getTypeElement(CharSequence)` tra `TypeElement` theo tên, trả `null` nếu không tìm được. Dữ liệu đến từ nguồn, classpath và module path mà compiler đang xử lý. Từ Java 9, có overload nhận `ModuleElement` khi cần xác định module chứa type.

Nếu đã có `TypeElement`:

~~~java
Name simple = type.getSimpleName();       // Derived
Name qualified = type.getQualifiedName(); // demo.Derived
ElementKind kind = type.getKind();         // CLASS
TypeMirror mirror = type.asType();
~~~

- `getSimpleName()` lấy tên đơn; `getQualifiedName()` lấy tên đầy đủ.
- `Name.contentEquals("Derived")` so sánh nội dung với một chuỗi; `Name` không đơn giản chỉ là một String.
- `Elements.getBinaryName(TypeElement)` trả binary name khi cần dùng ở mức JVM; nested classes có thể khác về cách đặt tên so với qualified name.
- `getKind()` giúp kiểm tra khai báo là `CLASS`, `INTERFACE`, `FIELD`, `METHOD`, `PARAMETER`... trước khi ép kiểu.

Tránh làm `(TypeElement) element` nếu chưa biết `element.getKind()`. Với processor xử lý nhiều nhóm annotation targets, sai cast là lỗi thực tế rất thường gặp.

### 3.2. Khai báo trực tiếp so với member được kế thừa

~~~java
var ownDeclarations = type.getEnclosedElements();
var allMembers = elements.getAllMembers(type);
~~~

- `getEnclosedElements()` liệt kê phần tử **được khai báo trực tiếp** bên trong type (gồm những elements compiler mô hình hóa tương ứng).
- `getAllMembers(type)` liệt kê cả **members được kế thừa**; không phải mọi phần tử trong danh sách đều được khai báo bởi `type`.
- `member.getEnclosingElement()` giúp xác định nơi khai báo field/method.
- Không dựa vào thứ tự mảng/list returned làm quy tắc sort cố định cho generated code.

Ví dụ `Derived` thừa hưởng field `Base.value`. `Derived.getEnclosedElements()` không chứa khai báo này như field riêng, nhưng `elements.getAllMembers(derived)` có thể tìm field ấy. Muốn tính **kiểu field được kế thừa sau khi thay T thành String**, cần `Types.asMemberOf`, không chỉ `VariableElement.asType()` của field gốc.

### 3.3. Xét override và hiding theo quy tắc Java

~~~java
boolean override = elements.overrides(
    derivedMethod, baseMethod, derivedTypeElement
);
~~~

`Elements.overrides(overrider, overridden, type)` trả kết quả dựa trên Java method overriding rules, không chỉ tên giống nhau. Hai methods có cùng tên nhưng khác parameters không nhất thiết override. Cũng không xem static hiding là instance overriding.

`Elements.hides(hider, hidden)` dùng cho quan hệ **hiding** trong các trường hợp ngôn ngữ định nghĩa. Khi viết processor kiểm tra contract của interface hoặc annotation đặt trên method, hãy xác định cần override hay hiding rồi chọn đúng API.

### 3.4. Đọc annotations qua mô hình compile time

`Element.getAnnotationMirrors()` trả `AnnotationMirror` cho annotations **được khai báo trực tiếp** trên element, không yêu cầu annotation có `RetentionPolicy.RUNTIME`. `Elements.getAllAnnotationMirrors(element)` có thể bổ sung các annotation được kế thừa theo quy tắc `@Inherited` cho class declarations; không có nghĩa annotation từ method cha được chuyển sang method override.

Muốn lấy annotation element values bao gồm mặc định, dùng `elements.getElementValuesWithDefaults(annotationMirror)`. Điều này khác với việc đọc reflection runtime:

- Annotation processor làm việc **lúc compile**, có thể nhìn thấy annotation `SOURCE`.
- Runtime reflection thường cần annotation `RUNTIME` và binary đã biên dịch.
- `AnnotationMirror` và `Class<?>, java.lang.annotation.Annotation` là hai mô hình khác nhau; đừng dựa vào `Class.forName` để truy vấn nguồn Java chưa có bytecode.

## 4. Dùng Types để kiểm tra kiểu và quan hệ kiểu

### 4.1. isSameType — hai TypeMirror có cùng kiểu không?

~~~java
boolean same = types.isSameType(left, right);
~~~

`Types.isSameType` so sánh theo mô hình Java type system. Không dùng `left == right`, `left.equals(right)` hoặc so hai `toString()` như phép so sánh semantic bắt buộc; cùng một kiểu có thể được các compiler implementations biểu diễn khác nhau.

Ví dụ `List<String>` và `List<Object>` không cùng kiểu. Cần lưu ý API có quy tắc đặc biệt: **hai wildcard types không được `isSameType` coi là cùng kiểu** theo contract của hàm này.

### 4.2. isSubtype — quan hệ kiểu con

~~~java
boolean childSubtype = types.isSubtype(child.asType(), baseOfString);
~~~

`isSubtype(t1, t2)` hỏi t1 có phải **subtype** của t2 không. Với `Derived extends Base<String>`, `isSubtype(Derived, Base<String>)` là true, còn `isSubtype(Base<String>, Derived)` là false.

Tạo type `Base<String>` phù hợp thay vì đoán từ class declaration:

~~~java
TypeElement base = elements.getTypeElement("demo.Base");
TypeElement stringType = elements.getTypeElement("java.lang.String");
DeclaredType baseOfString = types.getDeclaredType(
    base, stringType.asType()
);
~~~

`base.asType()` biểu diễn kiểu liên quan tới declaration generic `Base<T>`, **không đồng nghĩa** với `Base<String>`. Việc dựng `DeclaredType` với type argument rõ ràng giúp phép kiểm tra quan hệ kiểu phản ánh đúng specialization.

### 4.3. isAssignable — có thể gán được không?

~~~java
boolean canAssign = types.isAssignable(sourceType, targetType);
~~~

Khác với `isSubtype`, `Types.isAssignable` kiểm tra khả năng gán giá trị của một kiểu vào biến kiểu kia theo Java assignment compatibility. Một số trường hợp conversion (ví dụ boxing/unboxing) khiến kết quả hai phép kiểm tra có thể khác nhau.

Ví dụ quan trọng:

~~~java
List<String> names;
List<Object> objects;
~~~

Hai dòng này là **field declarations minh họa**, giả định có import `java.util.List`. Java generics **invariant**: `String <: Object` **không suy ra** `List<String> <: List<Object>`. Vì vậy `types.isAssignable(names.asType(), objects.asType())` là false khi mirrors tương ứng hai declarations đó.

Nếu API muốn chấp nhận `List<? extends Object>`, phải lấy đúng wildcard type theo JLS và so kiểu đó; không “tạm bỏ” generic arguments để làm cho test pass.

### 4.4. erasure — bỏ generic information có chủ đích

~~~java
TypeMirror erased = types.erasure(names.asType());
~~~

Với `names` có kiểu `List<String>`, kết quả hiển thị dạng `java.util.List`. Erasure có ích khi xử lý JVM-level signatures hoặc compatibility, nhưng **làm mất** thông tin generic type arguments. Nếu mục tiêu là phân biệt `List<String>` với `List<Object>` thì không erasure trước khi kiểm tra.

### 4.5. asMemberOf — thay thế generic parameter ở lớp kế thừa

Giả sử:

~~~java
class Base<T> { public T value; }
class Derived extends Base<String> {}
~~~

Dùng:

~~~java
DeclaredType derivedType = (DeclaredType) derived.asType();
TypeMirror inheritedFieldType = types.asMemberOf(
    derivedType, baseValueField
);
~~~

`baseValueField` là `VariableElement` của khai báo `Base.value`. Kết quả lúc xét từ `Derived` là `java.lang.String`, không phải `T`. API này rất quan trọng khi processor tạo serializer/mapper/validator cho các members kế thừa từ generic base classes.

**Không** gọi `asMemberOf` với element không là thành viên hợp lệ của containing type; API có thể ném `IllegalArgumentException`. Kiểm tra membership và `TypeKind` trước khi ép `TypeMirror` sang `DeclaredType`.

## 5. Từ Elements đến Types: quy trình kiểm tra thực tiễn

Một quy trình an toàn gồm:

1. **Chọn symbol cần phân tích**: `elements.getTypeElement(qualifiedName)` hoặc nhận `Element` từ `RoundEnvironment`.
2. **Kiểm tra có tồn tại và đúng ElementKind**: không dereference khi `null`, không cast trước khi xác minh field/method/type.
3. **Tìm member theo yêu cầu**: `getEnclosedElements` cho khai báo trực tiếp, `getAllMembers` nếu cần inherited members.
4. **Lấy TypeMirror**: `element.asType()`; khi cần generic substitution dùng `types.asMemberOf` trong containing type thích hợp.
5. **Chọn câu hỏi type rõ ràng**: same type (`isSameType`), subtype (`isSubtype`), assignment (`isAssignable`), erasure (`erasure`).
6. **So relation của method**: `elements.overrides` hoặc `elements.hides` thay vì so tên thủ công.
7. **Báo diagnostic đúng nguồn**: công cụ sản xuất thật nên dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, msg, element)` với element cần chỉ tới.

| Cần kiểm tra | API phù hợp | Tránh |
| --- | --- | --- |
| Tên lớp đầy đủ | `TypeElement.getQualifiedName()` | Chỉ so `getSimpleName()` |
| Kiểu có tồn tại ở build hiện tại | `elements.getTypeElement(...)` | `Class.forName` trong processor |
| Chỉ khai báo trực tiếp | `getEnclosedElements()` | Dùng danh sách inherited rồi xem tất cả là trực tiếp |
| Bao gồm inherited members | `elements.getAllMembers(...)` | Chỉ quét source fields của subclass |
| Type equivalence | `types.isSameType(...)` | So `toString()` |
| Quan hệ con–cha | `types.isSubtype(...)` | Phân tích tên generic bằng chuỗi |
| Assignment compatibility | `types.isAssignable(...)` | Cho rằng giống hoàn toàn `isSubtype` |
| Generic substitution | `types.asMemberOf(...)` | Dùng kiểu `T` của member gốc như kiểu đã specialization |
| Method overriding | `elements.overrides(...)` | Chỉ so method name |
| Annotation metadata lúc compile | `getAnnotationMirrors()`, `Elements.getElementValuesWithDefaults` | Chỉ dựa vào runtime reflection |

## 6. Ví dụ cần giải bài toán gì?

Ta sẽ kiểm tra các declarations sau trong một **annotation processor**:

- `demo.Base<T>` chứa field `T value` và method `T get()`.
- `demo.Derived extends Base<String>` kế thừa field, ghi đè method bằng `String get()` và có hai fields `List<String> names`, `List<Object> objects`.
- Processor sẽ tìm tên `demo.Derived`, xác nhận kind/supertype, kiểm tra subtype/assignability/generic invariance, tìm field inherited, xác nhận `asMemberOf` và quan hệ override.
- Processor cũng thử lookup một type không có mặt để minh họa kết quả `null`.

Ví dụ sử dụng **hai file Java**, không cần một `main`. Output được in khi **javac biên dịch model và gọi processor**, không phải khi chạy chương trình bằng `java`.

## 7. Ví dụ Java 17 hoàn chỉnh, đã kiểm chứng

Tạo cấu trúc:

~~~text
project/
├── ModelInspector.java
└── demo/
    └── Model.java
~~~

### File ModelInspector.java

~~~java
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.type.*;
import javax.lang.model.util.*;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ModelInspector extends AbstractProcessor {
    private boolean printed = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations, RoundEnvironment round) {
        if (printed || round.processingOver()) return false;
        Elements elements = processingEnv.getElementUtils();
        Types types = processingEnv.getTypeUtils();

        TypeElement child = elements.getTypeElement("demo.Derived");
        TypeElement parent = elements.getTypeElement("demo.Base");
        TypeElement string = elements.getTypeElement("java.lang.String");

        VariableElement names = null, objects = null;
        ExecutableElement derivedMethod = null, baseMethod = null;
        VariableElement baseValue = null;
        for (Element e : child.getEnclosedElements()) {
            if (e.getSimpleName().contentEquals("names")) names = (VariableElement) e;
            if (e.getSimpleName().contentEquals("objects")) objects = (VariableElement) e;
            if (e.getKind() == ElementKind.METHOD &&
                    e.getSimpleName().contentEquals("get")) derivedMethod = (ExecutableElement)e;
        }
        for (Element e : parent.getEnclosedElements()) {
            if (e.getSimpleName().contentEquals("value")) baseValue = (VariableElement)e;
            if (e.getKind() == ElementKind.METHOD &&
                    e.getSimpleName().contentEquals("get")) baseMethod = (ExecutableElement)e;
        }
        DeclaredType baseOfString = types.getDeclaredType(parent, string.asType());
        boolean inheritedField = elements.getAllMembers(child).stream()
             .anyMatch(e -> e.getKind() == ElementKind.FIELD &&
                  e.getSimpleName().contentEquals("value"));
        System.out.println("type=" + child.getQualifiedName());
        System.out.println("kind=" + child.getKind());
        System.out.println("simpleName=" + child.getSimpleName());
        System.out.println("supertype=" + child.getSuperclass());
        System.out.println("subtype=" + types.isSubtype(child.asType(), baseOfString));
        System.out.println("assignable=" + types.isAssignable(child.asType(), baseOfString));
        System.out.println("reverseSubtype=" + types.isSubtype(baseOfString, child.asType()));
        System.out.println("sameListType=" + types.isSameType(names.asType(), objects.asType()));
        System.out.println("assignListType=" + types.isAssignable(names.asType(), objects.asType()));
        System.out.println("erasure=" + types.erasure(names.asType()));
        System.out.println("inheritedField=" + inheritedField);
        System.out.println("memberType=" + types.asMemberOf((DeclaredType)child.asType(), baseValue));
        System.out.println("overrides=" + elements.overrides(derivedMethod, baseMethod, child));
        System.out.println("missing=" + (elements.getTypeElement("demo.Missing") == null));
        printed = true;
        return false;
    }
}
~~~

Đây là bản **demo tối thiểu** với tên kiểu/field cố định. Nó giả định các elements tồn tại đúng source mẫu. Processor tổng quát phải kiểm tra `null` và `ElementKind` trước khi cast để không văng `NullPointerException`/`ClassCastException`, đồng thời xử lý overloads chính xác.

### File demo/Model.java

~~~java
package demo;
import java.util.List;

class Base<T> {
    public T value;
    public T get() { return value; }
}

class Derived extends Base<String> {
    public List<String> names;
    public List<Object> objects;
    @Override public String get() { return "ok"; }
}
~~~

Hai class ở đây là package-private và có thể cùng nằm trong file `Model.java`. Processor trong default package vẫn tìm thấy chúng bằng `Elements.getTypeElement` khi `javac` biên dịch.

### Lệnh compile và kết quả

Đứng ở thư mục `project`, dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -d processor ModelInspector.java
javac --release 17 -encoding UTF-8 -cp processor -processorpath processor -processor ModelInspector -d classes demo/Model.java
~~~

Lệnh thứ nhất tạo bytecode của processor. Lệnh thứ hai chỉ định nó bằng `-processor ModelInspector`, cho phép javac nạp từ `-processorpath processor` và in kiểm tra ngay trong quá trình biên dịch. **Không cần** chạy `java ModelInspector` vì class processor không khai báo `main`.

**Stdout thực tế của lệnh javac thứ hai** (đã thử bằng JDK với `--release 17`):

~~~text
type=demo.Derived
kind=CLASS
simpleName=Derived
supertype=demo.Base<java.lang.String>
subtype=true
assignable=true
reverseSubtype=false
sameListType=false
assignListType=false
erasure=java.util.List
inheritedField=true
memberType=java.lang.String
overrides=true
missing=true
~~~

### Giải thích từng kết quả

1. `type`, `kind` và `simpleName` được lấy từ `TypeElement`; đây là thông tin declaration, không phải `Class<?>` runtime.
2. `supertype=demo.Base<java.lang.String>` cho thấy compiler giữ thông tin generic arguments trong `TypeMirror`.
3. `subtype=true`, `assignable=true`: `Derived` là subtype và có thể gán vào biến kiểu `Base<String>`.
4. `reverseSubtype=false`: `Base<String>` không phải subtype của `Derived`.
5. `sameListType=false`: `List<String>` và `List<Object>` khác kiểu.
6. `assignListType=false`: type invariance khiến `List<String>` không gán được cho `List<Object>`.
7. `erasure=java.util.List`: thông tin type argument bị loại theo Java erasure.
8. `inheritedField=true`: `Elements.getAllMembers` nhìn thấy field `value` của `Base`.
9. `memberType=java.lang.String`: `Types.asMemberOf` thay type variable `T` thành `String` khi xét field qua Derived.
10. `overrides=true`: `Derived.get()` override `Base.get()`, bao gồm generic return specialization.
11. `missing=true`: compiler lookup `demo.Missing` không thấy khai báo trong môi trường này nên trả `null`.

## 8. Những lỗi thường gặp

### So sánh TypeMirror qua toString()

`TypeMirror.toString()` hữu ích cho log nhưng không được dùng làm bộ so sánh semantic. Generic capture, type variables và wildcard representations khiến chuỗi hiển thị không thay thế được `types.isSameType`, `isSubtype` hay `isAssignable`.

### Nhầm Base<T> và Base<String>

`parent.asType()` thuộc generic declaration, không phải kiểu instantiation `Base<String>` đang cần để kiểm tra. Phải tạo mirror bằng `types.getDeclaredType(parent, string.asType())` hoặc lấy một type mirror thực sự đúng ngữ cảnh source.

### Xem tên phương thức giống nhau là override

`getSimpleName()` giống nhau không đủ; overloads, parameters, static/instance, visibility, generics và covariance đều quan trọng. Dùng `elements.overrides(overrider, overridden, containingType)`.

### Đánh đồng isSubtype và isAssignable

Đây là hai quan hệ được Java định nghĩa khác nhau. `isSubtype` hỏi quan hệ trong type hierarchy; `isAssignable` xét phép gán hợp lệ, có thể liên quan conversions như boxing/unboxing.

### Bỏ qua tính invariant của generics

`String` là subtype của `Object` không làm `List<String>` tự trở thành subtype của `List<Object>`. Một processor kiểm tra API có `List<?>`, `List<? extends X>` hay `List<? super X>` cần dựng và kiểm tra đúng mirrors thay vì chỉ xem element type.

### Chỉ dùng getEnclosedElements để tìm member kế thừa

`Derived.getEnclosedElements()` không chứa khai báo `Base.value` như field của Derived. Dùng `elements.getAllMembers(derived)` và `getEnclosingElement()` để tìm nguồn; dùng `asMemberOf` nếu cần kiểu đã generic-specialized.

### Cast nhầm hoặc thiếu symbol

`getTypeElement` có thể trả `null`. `TypeMirror` có nhiều `TypeKind`, có thể gặp `ErrorType` trong compile environment chưa đầy đủ. Hãy kiểm tra trước khi ép `DeclaredType` hoặc truy cập element liên quan. Diagnostic nên chỉ vào source element đúng với `Messager`.

### Dùng reflection runtime thay cho compile-time model

`Class.forName("demo.Derived")` có thể thất bại đơn giản vì Java source vừa được compiler đọc và chưa có bytecode để load. `Elements` và `Types` tồn tại chính để xử lý mô hình nguồn/classpath tại compile time.

### Không kiểm soát processing rounds

Annotation processing có thể chạy nhiều round. Đừng in kết quả trùng hoặc tạo lại cùng source file trong mọi round. Khi code production sinh file, quản lý Filer và round semantics theo contract của processor.

## 9. Những API nên học tiếp

Các method liên quan trong API chuẩn:

| API | Khi nào hữu ích |
| --- | --- |
| `Types.directSupertypes(type)` | Tra direct supertypes |
| `Types.boxedClass(primitiveType)` | Chuyển primitive type sang boxed class element |
| `Types.unboxedType(type)` | Tìm primitive type tương ứng |
| `Types.getArrayType(componentType)` | Tạo array type mirror |
| `Types.getWildcardType(extendsBound, superBound)` | Tạo wildcard với bound |
| `Types.capture(type)` | Áp dụng capture conversion |
| `Types.isSubsignature(method1, method2)` | Xét quan hệ signature của executable types |
| `Elements.getBinaryName(typeElement)` | Lấy JVM binary name |
| `Elements.isFunctionalInterface(typeElement)` | Xét functional interface |
| `Elements.getElementValuesWithDefaults(annotationMirror)` | Lấy mapping element values gồm default |

Cần đọc đúng kiểu tham số của từng method. Ví dụ `Types.asMemberOf` đòi hỏi `DeclaredType` và element đúng membership, còn `boxedClass` nhận `PrimitiveType`; mọi API đều có preconditions.

## 10. Tự kiểm tra kiến thức

**1. Elements và Types khác nhau ở đâu?** `Elements` thao tác trên các **khai báo/symbols**, còn `Types` trên **kiểu Java** (`TypeMirror`) và các quan hệ giữa kiểu.

**2. Đọc simple name và qualified name bằng gì?** `TypeElement.getSimpleName()` và `getQualifiedName()`; khi so `Name` với chuỗi, có thể dùng `contentEquals`.

**3. Tại sao `elements.getTypeElement("demo.Missing")` trả null?** Compiler không tìm được type với tên đó trong compilation environment được cung cấp.

**4. Tìm field `Base.value` từ Derived như thế nào?** Dùng `elements.getAllMembers(derived)`, kiểm tra `getKind() == FIELD` và `getSimpleName()`; `getEnclosedElements()` chỉ cho declarations trực tiếp.

**5. Vì sao `List<String>` không gán được cho `List<Object>`?** Java generic classes invariant; không suy subtype của whole generic type chỉ từ type argument.

**6. Lấy kiểu thực sự của field `Base<T>.value` khi tham chiếu qua `Derived extends Base<String>` bằng gì?** `types.asMemberOf((DeclaredType) derived.asType(), baseValueField)` trả `String`.

**7. Kiểm tra method override chuẩn bằng gì?** `elements.overrides(childMethod, baseMethod, childType)`; không tự so tên.

**8. Có thể đọc SOURCE-retained annotation bằng processor không?** Có, vì processor thao tác trên compiler element/annotation mirrors trong compile phase; runtime reflection thì không có annotation SOURCE lưu ở class file đích.

## 11. Tài liệu chính thức

- Java SE 21 API — **Elements**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Elements.html
- Java SE 21 API — **Types**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Types.html
- Java SE 21 API — **Element, TypeElement, ExecutableElement**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/package-summary.html
- Java SE 21 API — **TypeMirror, DeclaredType, TypeKind**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/type/package-summary.html
- Java SE 21 API — **ProcessingEnvironment và AbstractProcessor**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- JLS Java SE 21 — **Types, Values, Variables `4** và **Methods `8.4**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html và https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4

**Ghi nhớ:** trong annotation processor, hãy hỏi trước “mình cần kiểm tra **khai báo** hay **kiểu**?”. Đối với tên, kind, members, method overriding và annotations của khai báo, chọn `Elements`. Đối với equality, subtype, assignability, erasure và generic substitution, chọn `Types`. Kết hợp hai nhóm API giúp công cụ thực thi đúng Java language semantics, không dựa trên phỏng đoán từ tên chuỗi hoặc runtime reflection.