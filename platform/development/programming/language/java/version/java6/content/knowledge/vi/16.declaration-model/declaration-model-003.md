# TypeMirror, DeclaredType, TypeVariable và WildcardType trong mô hình khai báo Java

`javax.lang.model` là API chuẩn để **mô tả các khai báo và kiểu dữ liệu Java tại thời điểm biên dịch**, thường dùng trong annotation processor, code generator, static analysis và công cụ xử lý mã nguồn. Bốn interface **`TypeMirror`, `DeclaredType`, `TypeVariable` và `WildcardType`** giúp chương trình hiểu các kiểu như `List<String>`, `T extends Number` và `List<? super Integer>` mà **không cần tải class bằng reflection**.

Các API này có từ Java 6, nằm trong module `java.compiler`, và **vẫn được hỗ trợ trong Java 17+ cũng như JDK hiện hành**. Những ví dụ bên dưới sử dụng annotation processor Java 17-compatible và thao tác trên type model thực từ `javac`.

**Mục tiêu:** phân biệt *một khai báo* với *một lần sử dụng kiểu*, đọc chính xác tham số generic và bounds, hiểu wildcard/capture, rồi dùng `Types` để so sánh kiểu đúng ngữ nghĩa.

## 1. Vì sao phải có TypeMirror?

Ví dụ:

```java
// Mã minh họa, chưa phải chương trình độc lập:
class Holder<T extends Number> {
    java.util.List<String> names;
    java.util.List<? extends Number> numbers;
    T value;
}
```

Trong lúc compiler xử lý đoạn mã, nó cần biết:

- `Holder` là **khai báo** class nào? Có type parameter nào?
- `names` có kiểu **`List<String>`** chứ không chỉ `List`.
- `numbers` chứa một **wildcard `? extends Number`**; đó không phải một type variable được developer đặt tên.
- `value` có kiểu **`T`**, với upper bound `Number`; `T` không phải `Number` và cũng không phải một class runtime có thể nạp độc lập.
- Hai lần dùng cùng khai báo `List` có thể có các type arguments khác nhau.

API phản ánh các khía cạnh đó bằng hai nhóm:

| Nhóm | Đại diện | Trả lời câu hỏi |
| --- | --- | --- |
| **Element model** | `Element`, `TypeElement`, `TypeParameterElement`, `VariableElement`, `ExecutableElement` | “Khai báo nào, tên gì, nằm ở đâu, có các member/annotation nào?” |
| **Type model** | `TypeMirror` và các subtype, kết hợp `Types` | “Biểu thức/biến/kiểu được sử dụng với type arguments và bounds nào?” |

Ví dụ, `TypeElement` của `java.util.List` đại diện **khai báo interface List**; `DeclaredType` của `List<String>` đại diện **một lần sử dụng List với argument String**. Hai `DeclaredType` cho `List<String>` và `List<Integer>` có thể trả về **cùng một `TypeElement`** ở `asElement()`, nhưng có danh sách `getTypeArguments()` khác nhau.

**Không nhầm với reflection:** `java.lang.reflect.Type` và `Class<?>` làm việc từ góc độ runtime; `javax.lang.model.type.TypeMirror` là mô hình compile-time, có thể mô tả cả source mới đang biên dịch hoặc type không thể `Class.forName(...)` được.

## 2. `TypeMirror`: giao diện gốc của kiểu

`TypeMirror` là interface cơ sở cho các kiểu trong Java language model. Đối tượng kiểu cung cấp:

- `getKind()` → một giá trị `TypeKind` xác định loại kiểu;
- `accept(TypeVisitor<R,P>, P)` → dùng visitor để phân tích theo loại một cách có cấu trúc;
- `getAnnotationMirrors()` → chú giải trên **type use** nếu có;
- `toString()` → biểu diễn hữu ích cho debugging, **không nên dùng làm bộ phân tích type chính thức**.

`TypeMirror` không phải một supertype Java có phương thức `getTypeArguments()` cho mọi trường hợp: chỉ `DeclaredType` mới có phương thức đó. Muốn đọc bounds của type variable/wildcard phải phân nhánh theo `TypeKind` hoặc dùng visitor.

### Một số giá trị `TypeKind` quan trọng

| `TypeKind` | Dạng source / tình huống | Interface phù hợp |
| --- | --- | --- |
| `DECLARED` | `String`, `List<String>`, `Map<K,V>`, raw class/interface | `DeclaredType` |
| `TYPEVAR` | `T`, `E`, type variable do wildcard capture tạo | `TypeVariable` |
| `WILDCARD` | `?`, `? extends Number`, `? super Integer` | `WildcardType` |
| `ARRAY` | `int[]`, `String[]`, `T[]` | `ArrayType` |
| `INT`, `BOOLEAN`, v.v. | Kiểu nguyên thủy | `PrimitiveType` |
| `VOID` | Return type `void` | `NoType` |
| `NULL` | Kiểu null | `NullType` |
| `EXECUTABLE` | Kiểu chữ ký method/constructor | `ExecutableType` |
| `INTERSECTION` | Bounds giao nhau, ví dụ `Number & Comparable<T>` | `IntersectionType` |
| `UNION` | Multi-catch như `IOException | SQLException` | `UnionType` |
| `ERROR` | Kiểu class/interface không thể giải quyết tại compile time | `ErrorType` |
| `NONE` | Pseudo-type trong trường hợp không có kiểu phù hợp | `NoType` |

`TypeKind.ERROR` đáng chú ý: một symbol chưa được resolve vẫn có thể xuất hiện trong mô hình. Khi phân tích source đang lỗi, **đừng giả định mọi kiểu được báo đều là `DECLARED` hợp lệ**.

### Cách phân nhánh

```java
// Mảnh code minh họa, mirror là TypeMirror đã có:
switch (mirror.getKind()) {
    case DECLARED -> {
        DeclaredType declared = (DeclaredType) mirror;
        // Đọc declared.getTypeArguments().
    }
    case TYPEVAR -> {
        TypeVariable variable = (TypeVariable) mirror;
        // Đọc variable.getUpperBound().
    }
    case WILDCARD -> {
        WildcardType wildcard = (WildcardType) mirror;
        // Đọc extends/super bound (có thể null).
    }
    default -> {
        // Xử lý ARRAY, ERROR, primitives, v.v.
    }
}
```

Đây là **mảnh xử lý cần import `javax.lang.model.type.*`**, không phải chương trình độc lập. Có thể thay `switch` bằng `TypeVisitor` và `mirror.accept(...)` khi xây bộ phân tích nhiều loại kiểu. Documentation của `TypeMirror` khuyên dùng `getKind()` hoặc visitor; dựa hoàn toàn vào `instanceof` không luôn là lựa chọn tốt vì implementation có thể cho một object triển khai nhiều subinterface.

## 3. `DeclaredType`: class/interface type khi được sử dụng

`DeclaredType extends ReferenceType` mô tả kiểu class hoặc interface, bao gồm:

- Kiểu thường: `java.lang.String`, `java.lang.Number`;
- Parameterized type: `java.util.List<java.lang.String>`;
- Raw generic type: `java.util.List` không có type arguments cụ thể;
- Một kiểu nested member mang generic arguments.

Các phương thức chính:

| Phương thức | Kết quả | Lưu ý |
| --- | --- | --- |
| `asElement()` | `Element` tương ứng khai báo class/interface | Có thể cast thành `TypeElement` sau khi kiểm tra ngữ cảnh. |
| `getTypeArguments()` | Danh sách các **actual type arguments** của lần sử dụng | Có thể là `DeclaredType`, `TypeVariable`, `WildcardType` hoặc dạng khác hợp lệ. |
| `getEnclosingType()` | Kiểu enclosing instance của inner class, hoặc `NoType` loại `NONE` | Không đồng nghĩa mọi nested class đều có enclosing instance. |
| `getKind()` | `DECLARED` cho declared type bình thường | `ErrorType` có kind `ERROR`, cần chú ý riêng. |

Ví dụ:

```java
// Mảnh source Java để minh họa cấu trúc generic:
java.util.Map<String, java.util.List<Integer>> nested;
```

Type model có thể hình dung:

```text
DeclaredType: java.util.Map<java.lang.String,java.util.List<java.lang.Integer>>
  asElement()             -> TypeElement java.util.Map
  getTypeArguments()[0]   -> DeclaredType java.lang.String
  getTypeArguments()[1]   -> DeclaredType java.util.List<java.lang.Integer>
                              getTypeArguments()[0] -> DeclaredType java.lang.Integer
```

Với `List<String>`, `getTypeArguments().get(0)` là kiểu `String`; với `List<? extends Number>`, phần tử đầu là `WildcardType`, **không phải `Number`**. Nếu muốn hiểu kiểu tham số, phải kiểm tra kind của từng argument.

### Raw type và nongeneric type

Danh sách type arguments rỗng **chưa đủ để kết luận kiểu là raw**. Cả `String` (không khai báo generic parameters) và `List` (raw use của interface generic) đều có thể có danh sách rỗng. Cần đối chiếu `TypeElement.getTypeParameters()` của khai báo tương ứng và bối cảnh kiểu enclosing.

Đừng gọi `getTypeArguments().get(0)` mà không kiểm tra kích thước danh sách. `DeclaredType` lồng nhau cũng chỉ trả về arguments của **kiểu trong cùng**, không mặc định gộp arguments từ outer type.

### Từ declared use về declaration

```java
// Mảnh code tích hợp trong annotation processor:
DeclaredType declared = (DeclaredType) variableElement.asType();
TypeElement declaration = (TypeElement) declared.asElement();

String qualifiedName = declaration.getQualifiedName().toString();
List<? extends TypeMirror> actualArguments = declared.getTypeArguments();
```

`variableElement` ở đây là `VariableElement` có kiểu class/interface; cần kiểm tra `getKind()==DECLARED` trước khi cast. Nếu code chỉ cần type name có cấu trúc, dùng `TypeElement.getQualifiedName()` thay vì cắt chuỗi từ `DeclaredType.toString()`.

## 4. `TypeVariable`: kiểu biến `T`, `E` hay capture variable

`TypeVariable extends ReferenceType` mô tả các **type variables**, thường là tham số generic được khai báo bởi class, interface, method hoặc constructor.

Ví dụ:

```java
// Source minh họa:
class Sample<T extends Number & Comparable<T>> {
    T value;
}
```

- `T` là **type variable**; `value.asType().getKind() == TYPEVAR`.
- `TypeVariable.getUpperBound()` trả bound bên trên của `T`.
- Trong ví dụ có **hai bounds**, upper bound có `TypeKind.INTERSECTION`, biểu diễn `Number & Comparable<T>`.
- `TypeVariable.getLowerBound()` với type parameter khai báo bình thường trả `NullType` (`TypeKind.NULL`), không trả Java `null`.
- `TypeVariable.asElement()` chỉ tới element tương ứng với type variable; với `T` khai báo tường minh, đó là type parameter element.

### `TypeVariable` so với `TypeParameterElement`

Hai abstraction khác nhau:

| API | Đại diện |
| --- | --- |
| `TypeParameterElement` | Khai báo tên tham số kiểu (ví dụ `T`), thuộc class/method nào, danh sách bounds đã khai báo. |
| `TypeVariable` | Kiểu được sử dụng bởi biến hoặc generic signature; có upper/lower bound và có thể hình thành do capture conversion. |

Lấy `TypeVariable` từ element khai báo:

```java
// Mảnh code dùng trong processor đã có TypeElement sample:
TypeParameterElement typeParameter = sample.getTypeParameters().get(0);
TypeVariable variable = (TypeVariable) typeParameter.asType();

TypeMirror upper = variable.getUpperBound();
TypeMirror lower = variable.getLowerBound();
```

Chú ý phải import `TypeParameterElement`, `TypeMirror` và `TypeVariable`. Với `T` không khai báo upper bound tường minh, compiler dùng `Object` làm upper bound. Nếu có nhiều bounds, kết quả là `IntersectionType`; có thể đọc `((IntersectionType)upper).getBounds()`. Lower bound bình thường là `NullType`, nhưng **captured type variable** có thể có lower bound mang ý nghĩa khác.

### Không đồng nhất `T` với bound của nó

Từ `T extends Number` không được kết luận `T` chính là `Number`. `T` đại diện kiểu nào đó bị ràng buộc bởi Number. Khi kiểm tra codegen/assignment, dùng `Types.isAssignable` và `isSubtype` theo tình huống, không so sánh tên `toString()` của hai kiểu.

## 5. `WildcardType`: dấu hỏi trong generic type arguments

`WildcardType` mô tả wildcard argument, ví dụ:

```java
// Source minh họa:
java.util.List<?> any;
java.util.List<? extends Number> producer;
java.util.List<? super Integer> consumer;
```

Các hàm chính:

- `getExtendsBound()`: trả **upper bound được khai báo tường minh** trong `? extends ...`, hoặc Java **`null`** nếu không có.
- `getSuperBound()`: trả **lower bound được khai báo tường minh** trong `? super ...`, hoặc Java **`null`** nếu không có.
- `getKind() == TypeKind.WILDCARD`.

Bảng phân tích:

| Wildcard | `getExtendsBound()` | `getSuperBound()` |
| --- | --- | --- |
| `?` | `null` | `null` |
| `? extends Number` | `Number` (TypeMirror) | `null` |
| `? super Integer` | `null` | `Integer` (TypeMirror) |

Chỉ một loại bound được khai báo cho một wildcard. Chú ý **`null` ở API này không có nghĩa kiểu `NullType`**. Đó là dấu hiệu không có bound tường minh. Trong khi đó, `TypeVariable.getLowerBound()` với `T` thông thường là **một `TypeMirror` có kind `NULL`**, hoàn toàn khác Java reference `null`.

### Wildcard không phải type variable

- `List<T>`: argument `T` là `TypeVariable`.
- `List<? extends Number>`: argument là `WildcardType` với bound Number.
- Sau **capture conversion** (`Types.capture(...)`), compiler có thể biểu diễn wildcard bằng một *captured type variable* mới để giải quyết các phép kiểm tra kiểu. Lúc đó, argument trong type đã capture có thể mang `TypeKind.TYPEVAR`. Không nên gọi wildcard ban đầu là type variable nếu chưa capture.

`? extends Number` thường phù hợp với nguồn dữ liệu được đọc như Number; `? super Integer` thường cho nơi nhận giá trị Integer. Quy tắc PECS (*Producer Extends, Consumer Super*) là gợi ý về cách khai báo generic API, nhưng khi viết analyzer cần đọc đúng `getExtendsBound` / `getSuperBound` thay vì đoán vai trò dựa trên tên field.

## 6. Ví dụ Java 17+ hoàn chỉnh: khám phá đủ bốn loại kiểu bằng annotation processor

Ví dụ dùng `javac` chạy processor trên một class mang `@InspectTypes`. Processor sẽ đọc các field `List<String>`, wildcard bounds, type variable `T` và các type arguments lồng nhau, sau đó dùng `Types` để so sánh.

Mã thực hành có **ba tệp** dưới cấu trúc:

```text
type-model-demo/
  src/
    demo/
      InspectTypes.java
      Sample.java
    tool/
      TypeModelProcessor.java
  build/                   (được tạo khi chạy lệnh)
    processor/
    classes/
```

### 6.1. Annotation marker

**`src/demo/InspectTypes.java`**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface InspectTypes {}
```

Annotation cần ở source để processor nhìn thấy trong lúc biên dịch; không cần runtime retention nếu ứng dụng không đọc annotation bằng reflection.

### 6.2. Class có các mẫu generic

**`src/demo/Sample.java`**

```java
package demo;

import java.util.List;
import java.util.Map;

@InspectTypes
public class Sample<T extends Number & Comparable<T>> {
    List<String> names;
    List<? extends Number> producer;
    List<? super Integer> consumer;
    List<?> unknown;
    T value;
    Map<String, List<Integer>> nested;
}
```

Đây là source hợp lệ. Không cần `main` vì nhiệm vụ của nó là **đầu vào cho processor**, không phải chương trình chạy runtime. Các field được khai báo để quan sát type model, không có thao tác runtime hoặc lỗi generics.

### 6.3. Processor đọc cấu trúc

**`src/tool/TypeModelProcessor.java`**

```java
package tool;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.type.TypeVariable;
import javax.lang.model.type.WildcardType;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.InspectTypes")
public final class TypeModelProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    private static VariableElement field(TypeElement owner, String name) {
        for (Element element : owner.getEnclosedElements()) {
            if (element.getKind() == ElementKind.FIELD
                    && element.getSimpleName().contentEquals(name)) {
                return (VariableElement) element;
            }
        }
        throw new IllegalArgumentException("No field: " + name);
    }

    private void report(String value) {
        processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE, value);
    }

    @Override
    public boolean process(Set<? extends TypeElement> annos,
                           RoundEnvironment round) {
        if (round.processingOver()) return false;

        TypeElement mark = processingEnv.getElementUtils()
                .getTypeElement("demo.InspectTypes");
        if (mark == null) return false;

        for (Element element : round.getElementsAnnotatedWith(mark)) {
            TypeElement sample = (TypeElement) element;
            Types types = processingEnv.getTypeUtils();

            DeclaredType names =
                    (DeclaredType) field(sample, "names").asType();
            DeclaredType producer =
                    (DeclaredType) field(sample, "producer").asType();
            DeclaredType consumer =
                    (DeclaredType) field(sample, "consumer").asType();
            DeclaredType unknown =
                    (DeclaredType) field(sample, "unknown").asType();

            TypeVariable t = (TypeVariable)
                    sample.getTypeParameters().get(0).asType();
            WildcardType ext = (WildcardType)
                    producer.getTypeArguments().get(0);
            WildcardType sup = (WildcardType)
                    consumer.getTypeArguments().get(0);
            WildcardType any = (WildcardType)
                    unknown.getTypeArguments().get(0);

            DeclaredType captured =
                    (DeclaredType) types.capture(producer);
            TypeMirror capturedArg = captured.getTypeArguments().get(0);

            report("owner=" + sample.getQualifiedName());
            report("names.kind=" + names.getKind());
            report("names.declaration=" +
                    ((TypeElement) names.asElement()).getQualifiedName());
            report("names.arg.kind=" +
                    names.getTypeArguments().get(0).getKind());
            report("T.kind=" + t.getKind());
            report("T.upper.kind=" + t.getUpperBound().getKind());
            report("T.lower.kind=" + t.getLowerBound().getKind());
            report("producer.arg.kind=" + ext.getKind());
            report("producer.extends=" + ext.getExtendsBound());
            report("producer.superAbsent=" + (ext.getSuperBound() == null));
            report("consumer.super=" + sup.getSuperBound());
            report("consumer.extendsAbsent=" + (sup.getExtendsBound() == null));
            report("unknown.hasBounds=" +
                    (any.getExtendsBound() != null ||
                     any.getSuperBound() != null));
            report("names.assignableToUnknown=" +
                    types.isAssignable(names, unknown));
            report("names.sameAsUnknown=" +
                    types.isSameType(names, unknown));
            report("erasure.names=" + types.erasure(names));
            report("captured.arg.kind=" + capturedArg.getKind());
            report("value.kind=" +
                    field(sample, "value").asType().getKind());
            report("nested.args=" +
                    ((DeclaredType) field(sample, "nested").asType())
                            .getTypeArguments().size());
        }
        return true;
    }
}
```

**Giải thích:**

1. `@SupportedAnnotationTypes` cho compiler biết processor nhận loại `demo.InspectTypes`. `getSupportedSourceVersion()` trả source version mà runtime compiler hỗ trợ; lệnh build dùng `--release 17` để giới hạn source mục tiêu.
2. `RoundEnvironment.getElementsAnnotatedWith(...)` tìm type cần phân tích. `TypeElement` đại diện khai báo `demo.Sample`.
3. `field(...)` tìm `VariableElement` theo tên field; `VariableElement.asType()` trả `TypeMirror`.
4. `names` là `DeclaredType`, `names.asElement()` trỏ về khai báo `java.util.List`, còn `names.getTypeArguments()` cho biết `String`.
5. `Sample<T ...>` có `TypeVariable T`, upper bound là `INTERSECTION`, lower bound là `NULL`.
6. `producer`/`consumer`/`unknown` đều là `DeclaredType` của `List` nhưng argument đầu lần lượt là `? extends Number`, `? super Integer` và `?`, có kind `WILDCARD`.
7. `Types.capture(producer)` mô hình hóa capture conversion; argument mới trở thành `TYPEVAR`, không còn là wildcard gốc.
8. `isAssignable(names, unknown)` true: một `List<String>` có thể gán vào biến `List<?>`. `isSameType(names, unknown)` false: hai kiểu không giống nhau.
9. `Messager` được dùng thay cho việc in trực tiếp ra stdout trong processor. Các dòng `Note: ...` hiển thị bằng công cụ compiler, không phải output từ chương trình `Sample`.

### 6.4. Lệnh biên dịch và kích hoạt processor

Tại thư mục `type-model-demo`:

```bash
mkdir -p build/processor build/classes
javac --release 17 -d build/processor src/tool/TypeModelProcessor.java
javac --release 17 -proc:only -processorpath build/processor -processor tool.TypeModelProcessor -d build/classes src/demo/InspectTypes.java src/demo/Sample.java
```

Tương đương trên PowerShell:

```powershell
New-Item -ItemType Directory -Force build/processor,build/classes | Out-Null
javac --release 17 -d build/processor src/tool/TypeModelProcessor.java
javac --release 17 -proc:only -processorpath build/processor -processor tool.TypeModelProcessor -d build/classes src/demo/InspectTypes.java src/demo/Sample.java
```

Lệnh đầu tạo processor class. Lệnh thứ hai chạy **annotation processing only** nhờ `-proc:only` (không tạo class output thông thường). `-processor` và `-processorpath` chọn processor tường minh, nên vẫn hoạt động theo chính sách bảo mật của `javac` từ JDK 23+.

**Compiler diagnostics đã kiểm chứng bằng `javac` JDK 24:**

```text
Note: owner=demo.Sample
Note: names.kind=DECLARED
Note: names.declaration=java.util.List
Note: names.arg.kind=DECLARED
Note: T.kind=TYPEVAR
Note: T.upper.kind=INTERSECTION
Note: T.lower.kind=NULL
Note: producer.arg.kind=WILDCARD
Note: producer.extends=java.lang.Number
Note: producer.superAbsent=true
Note: consumer.super=java.lang.Integer
Note: consumer.extendsAbsent=true
Note: unknown.hasBounds=false
Note: names.assignableToUnknown=true
Note: names.sameAsUnknown=false
Note: erasure.names=java.util.List
Note: captured.arg.kind=TYPEVAR
Note: value.kind=TYPEVAR
Note: nested.args=2
```

Đây là **diagnostics của compiler** (thường ở stderr), không nên gọi là stdout của chương trình `Sample`. Câu chữ diagnostic do `report(...)` tự tạo, nên phần text này được kiểm chứng ở môi trường thử nghiệm cụ thể; ở môi trường khác có thể có tiền tố và formatting khác.

## 7. Duyệt cấu trúc generic lồng nhau

Một `DeclaredType` chỉ cung cấp **actual type arguments của chính nó**. Ví dụ field `nested` trong `Sample` có hai arguments:

1. `String` — kind `DECLARED`;
2. `List<Integer>` — kind `DECLARED`, bên trong có một argument `Integer`.

Muốn phân tích cây generic, cần duyệt đệ quy, không chỉ xem phần tử `getTypeArguments().get(0)`:

```text
Map<String, List<Integer>>
  DeclaredType Map
    ├── DeclaredType String
    └── DeclaredType List
          └── DeclaredType Integer
```

Với mọi argument, đọc `getKind()` để quyết định:

- `DECLARED`: đi sâu vào `getTypeArguments()` nếu cần;
- `WILDCARD`: kiểm tra bound tường minh (có thể null);
- `TYPEVAR`: kiểm tra element/bounds, đồng thời tránh vòng lặp không dứt với `T extends Comparable<T>`;
- `ARRAY`: đọc component type qua `ArrayType.getComponentType()`;
- `ERROR`: báo type chưa resolve rõ ràng, tránh tiếp tục suy luận khi model không đáng tin.

### Vì sao cần kiểm soát vòng lặp?

Bound có thể **tự tham chiếu**:

```java
// Đoạn source minh họa:
class Chain<T extends Comparable<T>> {}
```

Duyệt naive `T` → upper `Comparable<T>` → argument `T` → upper `Comparable<T>` sẽ lặp vô hạn. Khi viết analyzer/generator, lưu visited stack hoặc giới hạn độ sâu và phân biệt reference đến cùng một type parameter với quá trình mở rộng nội dung type.

## 8. `Types`: so sánh kiểu theo nghĩa Java

`javax.lang.model.util.Types` là utility API do `processingEnv.getTypeUtils()` cung cấp, giúp phân tích các quan hệ ngữ nghĩa giữa các `TypeMirror`. Đây là **đối tác bắt buộc** khi làm việc nghiêm túc với generic types.

| Phương thức | Mục đích |
| --- | --- |
| `isSameType(t1, t2)` | Kiểm tra liệu hai mirrors biểu diễn cùng kiểu theo quy tắc model. |
| `isSubtype(t1, t2)` | Kiểm tra quan hệ subtype. |
| `isAssignable(t1, t2)` | Kiểm tra có thể gán giá trị kiểu `t1` vào biến kiểu `t2` hay không. |
| `erasure(t)` | Trả kiểu sau khi áp dụng type erasure. |
| `capture(t)` | Áp dụng capture conversion cho wildcard theo quy tắc Java. |
| `directSupertypes(t)` | Trả các supertype trực tiếp, có thay thế actual type arguments phù hợp. |
| `getDeclaredType(typeElement, typeArgs...)` | Dựng declared type từ khai báo và actual type arguments. |
| `getWildcardType(extendsBound, superBound)` | Dựng wildcard với upper hoặc lower bound. |
| `asMemberOf(containingType, memberElement)` | Xác định kiểu của một member khi được nhìn qua một parameterized containing type. |
| `isSubsignature(methodA, methodB)` | So sánh mối quan hệ chữ ký executable khi phù hợp. |

Không dùng `type1 == type2` hoặc `type1.equals(type2)` để quyết định hai kiểu **tương đương về ngữ nghĩa**. `TypeMirror.equals` là object equality thông thường; không bảo đảm object mirrors là singleton hoặc kết quả equals trùng với `Types.isSameType`.

### 8.1. Same type, subtype, assignable là ba câu hỏi khác nhau

Ví dụ `List<String>` và `List<?>`:

```java
// Mảnh tích hợp, names là DeclaredType List<String>,
// unknown là DeclaredType List<?>; types là Types.
boolean assignable = types.isAssignable(names, unknown); // true
boolean exactlySame = types.isSameType(names, unknown);   // false
```

Không nhầm `List<String>` thành subtype của `List<Object>`. Java generics nhìn chung **invariant**: từ `String extends Object` không suy ra `List<String> extends List<Object>`.

Tính assignable còn phụ thuộc conversion rules của Java (ví dụ boxing/unboxing trong ngữ cảnh phù hợp), nên không tự giả định `isSubtype` và `isAssignable` luôn cho cùng kết quả.

### 8.2. Erasure không có nghĩa generic arguments giống nhau

`Types.erasure(List<String>)` và `Types.erasure(List<Integer>)` đều cho kiểu raw `List`. Điều đó **không chứng minh** hai kiểu gốc giống nhau.

```java
// Mảnh code minh họa dùng types và names trong processor:
TypeMirror rawList = types.erasure(names);
System.out.println(rawList); // Với javac: java.util.List
```

`erasure` hữu ích khi kiểm tra signatures và liên hệ tới biểu diễn sau generic type erasure, nhưng cần giữ generic arguments nếu mục tiêu là validate compile-time API.

### 8.3. Capture conversion

Mô hình `List<? extends Number>` có argument `WILDCARD`. Khi `Types.capture(...)` được áp dụng, compiler tạo type variable nội bộ tượng trưng một kiểu chưa biết nhưng bị ràng buộc:

```java
// Mảnh code minh họa:
DeclaredType captured =
        (DeclaredType) types.capture(producer);
TypeMirror argument = captured.getTypeArguments().get(0);
boolean isCapturedVariable =
        argument.getKind() == TypeKind.TYPEVAR;
```

Kết quả `isCapturedVariable` là `true` trong ví dụ đã kiểm thử. Tên nội bộ của captured variable có thể được compiler hiển thị khác nhau; **không parse chuỗi `capture#...`** để xây logic.

### 8.4. Tạo kiểu có tham số qua `Types.getDeclaredType`

Khi có một `TypeElement` cho `java.util.List` và `TypeMirror` cho `java.lang.String`, có thể dựng `List<String>`:

```java
// Đoạn tích hợp bên trong annotation processor:
Types types = processingEnv.getTypeUtils();
TypeElement listElement = processingEnv.getElementUtils()
        .getTypeElement("java.util.List");
TypeElement stringElement = processingEnv.getElementUtils()
        .getTypeElement("java.lang.String");

DeclaredType listOfString =
        types.getDeclaredType(listElement, stringElement.asType());
```

Đây là **mảnh code**, cần import `Types`, `TypeElement` và `DeclaredType`, đồng thời xử lý null nếu tên type không tìm được. `getDeclaredType` kiểm tra số lượng/giá trị type arguments, không tự tạo class hoặc biên dịch code.

Tương tự:

```java
// Có thể đặt trong processor khi đã có Types types và TypeMirror numberType:
WildcardType covariant = types.getWildcardType(numberType, null);
WildcardType contravariant = types.getWildcardType(null, numberType);
WildcardType any = types.getWildcardType(null, null);
```

`getWildcardType` cho phép **upper bound hoặc lower bound hoặc không bound**, nhưng không nhận cả hai cùng lúc. Chỉ dùng reference types phù hợp làm bound.

### 8.5. `asMemberOf` và thay thế generic parameters

Giả sử:

```java
// Source minh họa:
class Box<T> {
    T value;
}
Box<String> box;
```

Khai báo field `value` có kiểu `T` trong `Box<T>`. Nhưng khi nhìn qua `Box<String>`, kiểu field đó là `String`. `Types.asMemberOf(DeclaredType containing, Element member)` giải quyết phép thay thế này. Nếu bạn chỉ gọi `member.asType()` mà bỏ context `Box<String>`, bạn vẫn có thể thấy `T`.

Ứng dụng: kiểm tra mapper, serializer, binding generator hoặc chuyển method signature qua kế thừa generic. Khi phân tích method, đôi lúc cần kiểu thành viên trong **declared receiver type cụ thể**, không chỉ kiểu gốc trên declaration.

## 9. Các giới hạn và trường hợp đặc biệt

### 9.1. Source đang lỗi: `ErrorType`

Nếu compiler chưa giải quyết được một tên kiểu, `TypeMirror.getKind()` có thể trả `ERROR`. `ErrorType` thuộc hệ declared/reference type, nhưng thường biểu thị mô hình chưa hoàn chỉnh. Một annotation processor tốt nên:

1. Phát hiện `ERROR` trước khi giả định fully resolved class.
2. Có thể hoãn xử lý tới round phù hợp nếu type sẽ được code generator khác tạo ra, nhưng không dựa vào việc lỗi tự biến mất vô điều kiện.
3. Báo diagnostic hữu ích khi không thể tiếp tục, thay vì crash vì cast sai hoặc classpath thiếu.

### 9.2. Intersection và nhiều bounds

`<T extends Number & Comparable<T>>` có upper bound kiểu `INTERSECTION`, không phải một `DeclaredType Number` đơn lẻ. Đọc từng bound qua `IntersectionType.getBounds()` khi thật sự cần phân tích đầy đủ constraints. Dùng `TypeVisitor` hoặc phân nhánh kind để không bỏ qua loại kiểu này.

### 9.3. Annotated type use

Java hỗ trợ **type-use annotations**. `TypeMirror` kế thừa `AnnotatedConstruct`, vì vậy `getAnnotationMirrors()` có thể phản ánh annotations trên type use như `@NonNull String` (tùy annotation và cách compiler cung cấp model). Đừng nhầm annotations trên **declaration element** với annotations trên **type occurrence**; hai vị trí có thể mang ý nghĩa khác nhau đối với analyzer.

### 9.4. Giới hạn của `toString()`

`toString()` giúp debug, nhưng không phải một serialized type format với hợp đồng grammar ổn định cho ứng dụng. Để xây output đúng: lấy tên từ `TypeElement`, type arguments từ `DeclaredType`, bounds từ `TypeVariable`/`WildcardType`, sau đó tự format theo định nghĩa API của bạn.

### 9.5. Thời điểm và phạm vi hợp lệ

`TypeMirror`/`Element` thuộc model của môi trường compile/processing cụ thể. Đừng cache chúng vào static global hay lưu qua nhiều compilation invocations rồi dùng lại như object runtime ổn định. Khi cần lưu metadata lâu dài, chuyển thành DTO tên kiểu, danh sách args và các ràng buộc phù hợp.

## 10. Annotation processing trong JDK hiện hành

Ví dụ sử dụng annotation processor không phải vì các interface `TypeMirror` chỉ dùng được cho annotation: các công cụ compiler khác cũng dùng model. Nhưng annotation processing là nơi dễ thực hành vì `ProcessingEnvironment` cung cấp ngay:

```java
Types types = processingEnv.getTypeUtils();
Elements elements = processingEnv.getElementUtils();
```

Đây là đoạn tích hợp trong processor, import `javax.lang.model.util.Types` và `Elements`.

Từ **JDK 23**, `javac` không mặc định chạy annotation processors khi chưa có cấu hình xử lý tường minh. Với công cụ mới, **chỉ định processor rõ ràng** (`-processor`, processor path/module path hay cấu hình build tool tương ứng) để tránh hành vi phụ thuộc vào classpath ngẫu nhiên. Ví dụ phần 6 dùng `-proc:only` và `-processor tool.TypeModelProcessor`, nên ý định chạy processor đã rõ.

Các IDE/build tools có thể tự quản lý annotation processing. Nếu processor không được gọi, đừng kết luận `TypeMirror` đã lỗi thời; cần kiểm tra toolchain, plugin cấu hình, processor discovery và source version.

**Điểm khác với runtime reflection:** analyzer dùng `TypeMirror` không yêu cầu class nguồn đã được build thành bytecode và không nên cố `Class.forName(...)` class do user vừa gửi nhưng chưa compile.

## 11. Lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Cast mọi `TypeMirror` thành `DeclaredType` | Primitive, array, wildcard, type variable, error... có kind khác. | Dùng `getKind()`/visitor rồi mới cast. |
| Tưởng `TypeElement` chính là `List<String>` | Element mô tả declaration `List`, không đại diện mọi lần dùng. | Dùng `DeclaredType` và `getTypeArguments()`. |
| Dùng `toString().split("<")` để parse generic | Nested generics, annotations, wildcard và implementation details làm parser dễ sai. | Duyệt type model theo kind/arguments/bounds. |
| So sánh bằng `==` hoặc `equals` để kiểm tra cùng kiểu | Object equality không tương đương semantic type equality. | Dùng `Types.isSameType`. |
| Cho rằng `List<String>` là `List<Object>` | Generic invariance bị hiểu sai. | Dùng `Types.isAssignable` và wildcard bounds đúng ngữ cảnh. |
| Nhầm `? extends X` thành `X` | Argument gốc là `WildcardType`, không phải DeclaredType X. | Đọc `getExtendsBound()`; cân nhắc `Types.capture` khi cần. |
| Nhầm `?` không bound với `TypeVariable.getLowerBound()` | Wildcard unbounded trả Java `null`, type variable lower thường là `NullType`. | Phân biệt null reference và `TypeKind.NULL`. |
| Bỏ qua `INTERSECTION` | Type variable có thể có nhiều upper bounds. | Dùng `IntersectionType.getBounds()`. |
| Duyệt bound `T extends Comparable<T>` vô hạn | Type graph có chu trình do F-bounded polymorphism. | Theo dõi visited stack hoặc giới hạn độ sâu. |
| Gán type name bằng `mirror.toString()` làm ID lâu dài | String rendering không phải API identity bền vững. | Đọc `TypeElement.getQualifiedName()` và cấu trúc arguments. |
| `List` raw bị hiểu là nongeneric | Cả raw và class nongeneric có thể trả args rỗng. | Đối chiếu declaration type parameters. |
| Bỏ qua `ErrorType` | Model có thể thiếu classpath hoặc source chưa resolve. | Xử lý `TypeKind.ERROR` trước khi suy luận. |
| Processor không chạy trên JDK 23+ | Không cấu hình processor tường minh. | Chỉ định `-processor`/processor path hoặc build tool config. |
| Dùng `Class.forName()` để truy cập class đang compile | Class chưa chắc có ở runtime classpath. | Dùng `Elements` và `Types` theo compile-time model. |
| Chỉ gọi `member.asType()` trên member generic | Bỏ mất substitution theo receiver type. | Dùng `Types.asMemberOf(...)` khi cần context. |

## 12. Checklist cho người viết processor/analyzer

1. Xác định đang làm việc với **declaration** (`Element`) hay **type use** (`TypeMirror`).
2. Lấy kind bằng `getKind()`; không cast theo giả định.
3. Với `DECLARED`, lấy declaration qua `asElement()` và actual arguments qua `getTypeArguments()`.
4. Với `TYPEVAR`, đọc upper/lower bounds; xem `INTERSECTION` nếu có nhiều bounds.
5. Với `WILDCARD`, kiểm tra `getExtendsBound()`/`getSuperBound()` có thể null.
6. Duyệt nested arguments có giới hạn chu trình, đặc biệt F-bounded type variables.
7. Dùng `Types.isSameType/isAssignable/isSubtype` đúng câu hỏi, không so sánh chuỗi.
8. Chỉ dùng `erasure` khi thật sự muốn bỏ generic information; đừng vô tình làm mất thông tin cần thiết.
9. Dùng `Types.capture` khi phân tích capture conversion, không nhầm type captured với wildcard ban đầu.
10. Kiểm tra `ERROR`, `NONE`, `ARRAY`, `INTERSECTION` trước các phép cast.
11. Khi phân tích member generic qua `Box<String>`, xem xét `Types.asMemberOf`.
12. Khóa Java source release/toolchain và kích hoạt annotation processor tường minh trong build hiện hành.
13. Viết unit/integration tests với `List<String>`, `List<?>`, `? extends`, `? super`, bounds giao nhau và raw type.
14. Chuyển kết quả model thành dữ liệu có cấu trúc khi cần lưu lâu dài, không giữ compiler model objects qua nhiều build.

## 13. Bài tập thực hành

**Bài tập 1 — Thêm raw type.** Thêm field `List raw;` vào `Sample`, rồi bổ sung báo cáo `getTypeArguments().size()` cho `raw` và `names`. Vì sao một danh sách arguments rỗng chưa chứng minh declaration là nongeneric?

**Bài tập 2 — Duyệt nested generics.** Từ field `nested`, lấy argument thứ 2 là `List<Integer>` rồi in argument `Integer` ở tầng tiếp theo. Không parse chuỗi `toString()`.

**Bài tập 3 — Bounds.** Đổi `T extends Number & Comparable<T>` thành `T extends Number`, chạy lại processor. Dự đoán `T.upper.kind` và giải thích sự thay đổi.

**Bài tập 4 — Wildcard.** In `getExtendsBound()` và `getSuperBound()` cho ba field `producer`, `consumer` và `unknown`; so sánh kết quả null/bound.

**Bài tập 5 — Capture.** So sánh `getKind()` của argument trong `producer` trước và sau `types.capture(producer)`; giải thích tại sao captured variable có thể có bound dù wildcard không có tên khai báo.

**Bài tập 6 — Type relations.** Dựng `List<String>` và `List<Integer>` bằng `getDeclaredType`, so sánh `isSameType`, `isAssignable` và `erasure`. Không suy ra sự tương đương từ việc hai erasures giống nhau.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt giữa `TypeElement` và `DeclaredType` là gì?

**Đáp án:** `TypeElement` đại diện khai báo type như `List`; `DeclaredType` đại diện một cách dùng type, ví dụ `List<String>`, kèm actual arguments và enclosing type khi phù hợp.

**Câu 2.** `List<? extends Number>` có argument kind gì? Bản thân bound kind gì?

**Đáp án:** argument là `WILDCARD`. `getExtendsBound()` trả TypeMirror của `Number`, thường là `DECLARED`.

**Câu 3.** `T extends Number & Comparable<T>` có `getUpperBound().getKind()` là gì?

**Đáp án:** `INTERSECTION`, vì upper bound gồm nhiều ràng buộc. Với `T` khai báo bình thường, `getLowerBound().getKind()` là `NULL`.

**Câu 4.** Vì sao `WildcardType.getSuperBound()==null` khác `TypeVariable.getLowerBound().getKind()==NULL`?

**Đáp án:** trường hợp đầu là **không có lower bound được khai báo** (Java null reference); trường hợp sau là **một TypeMirror** đại diện null type.

**Câu 5.** `Types.erasure(List<String>)` giống `Types.erasure(List<Integer>)` có chứng minh chúng cùng type không?

**Đáp án:** không. Generic arguments bị xóa khi erasure; dùng `Types.isSameType` trên kiểu gốc để kiểm tra ngữ nghĩa.

**Câu 6.** Khi nào cần `Types.asMemberOf`?

**Đáp án:** khi phải biết kiểu member sau thay thế generic type parameters trong một containing type cụ thể, ví dụ field `T value` của `Box<T>` khi nhìn qua `Box<String>`.

**Câu 7.** Có thể lưu `TypeMirror` làm key xuyên các lần compile và dựa vào `equals` không?

**Đáp án:** không nên. Mirrors thuộc compilation/model environment; semantic comparisons nên dùng `Types` trong môi trường liên quan, dữ liệu lâu dài nên được chuẩn hóa thành cấu trúc độc lập.

## 15. Tài liệu chính thức đang áp dụng

- [TypeMirror — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html) — interface gốc, `TypeKind`, visitor, chú ý semantic comparison.
- [DeclaredType — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/DeclaredType.html) — class/interface type, actual arguments và enclosing type.
- [TypeVariable — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeVariable.html) — upper/lower bounds và capture conversion.
- [WildcardType — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/WildcardType.html) — wildcard `?`, `extends`, `super`.
- [TypeKind — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/TypeKind.html) — các kind hiện hành.
- [Types — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/util/Types.html) — comparison, capture, erasure, substitution và construction utilities.
- [TypeElement — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/TypeElement.html) — mô hình khai báo class/interface.
- [Javac command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — `--release`, `-processor`, `-proc:only`.

**Ghi nhớ:** `TypeMirror` là nền tảng mô hình kiểu tại compile time; **`DeclaredType`** biểu diễn class/interface use với actual arguments; **`TypeVariable`** biểu diễn biến kiểu và bounds; **`WildcardType`** biểu diễn `?` với upper/lower bound có thể thiếu. Muốn so sánh hoặc biến đổi các kiểu này một cách đáng tin, dùng **`Types`**, không dựa vào `toString()`, object equality hoặc runtime reflection.
