# TypeElement, ExecutableElement và VariableElement trong mô hình ngôn ngữ Java

## 1. Vì sao cần mô hình ngôn ngữ?

Khi viết **annotation processor** trong Java, chương trình xử lý diễn ra trong quá trình biên dịch. Tại thời điểm đó, compiler đang phân tích các khai báo kiểu, phương thức, constructor, trường và tham số. Processor cần một cách thống nhất để **mô tả những khai báo trong mã nguồn** mà không phải tải chúng thành đối tượng runtime bằng `Class.forName(...)`.

Java cung cấp **Language Model API** trong các package chủ yếu:

- `javax.lang.model.element`: mô tả **các phần tử của chương trình** — khai báo kiểu, phương thức, biến, package, annotation...
- `javax.lang.model.type`: mô tả **kiểu** của các phần tử dưới dạng `TypeMirror`.
- `javax.lang.model.util`: các tiện ích như `Elements`, `Types` và `ElementFilter`.
- `javax.annotation.processing`: hạ tầng annotation processing, gồm `AbstractProcessor`, `RoundEnvironment`, `ProcessingEnvironment`.

Ba interface quan trọng ở bài này là:

| Interface | Đại diện cho | Một số ví dụ |
| --- | --- | --- |
| `TypeElement` | Khai báo một **kiểu** | `class Invoice`, `interface Service`, `enum Status`, `@interface Marker` |
| `ExecutableElement` | Khai báo **phương thức, constructor hoặc loại phần tử thực thi phù hợp** | `int total(int count)`, `Invoice(String code)`, `String value();` trong annotation type |
| `VariableElement` | Khai báo **biến** ở nhiều loại vị trí | field `code`, parameter `count`, hằng enum, biến cục bộ nếu mô hình cung cấp |

**Ý chính:** các đối tượng trên là **biểu diễn cấu trúc chương trình do compiler cung cấp**, không phải đối tượng nghiệp vụ và không phải lời gọi thực thi method. Chúng cho processor biết một khai báo **là gì, có tên gì, có kiểu nào và liên hệ với khai báo khác ra sao**.

## 2. Cây `Element`: mối quan hệ giữa ba interface

Cả ba interface `TypeElement`, `ExecutableElement`, `VariableElement` đều kế thừa `Element`. Vì vậy có các phương thức chung:

- `getSimpleName()`: tên đơn giản của khai báo, như `Invoice` hoặc `total`.
- `getKind()`: phân loại chi tiết bằng `ElementKind`.
- `getModifiers()`: tập modifier như `PUBLIC`, `PRIVATE`, `STATIC` (nếu áp dụng).
- `getEnclosingElement()`: phần tử **bao quanh trực tiếp**, ví dụ field nằm trong class hoặc parameter thuộc method.
- `getEnclosedElements()`: các phần tử được khai báo trực tiếp bên trong một phần tử.
- `asType()`: lấy biểu diễn kiểu `TypeMirror` của phần tử.
- `getAnnotationMirrors()`: đọc các annotation được gắn trực tiếp ở mức mô hình ngôn ngữ.

Có thể hình dung mã nguồn sau:

```java
class Invoice {
    private String code;

    Invoice(String code) {
        this.code = code;
    }

    int total(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
```

và cấu trúc khái niệm:

```text
TypeElement: Invoice
├── VariableElement: code          (FIELD)
├── ExecutableElement: Invoice(...) (CONSTRUCTOR)
│   └── VariableElement: code      (PARAMETER)
└── ExecutableElement: total(...)   (METHOD)
    ├── VariableElement: quantity  (PARAMETER)
    └── VariableElement: unitPrice (PARAMETER)
```

Cây trên là **sơ đồ mô hình**, không phải output mặc định của compiler. Các mục tương ứng được khám phá qua `TypeElement.getEnclosedElements()`, `ExecutableElement.getParameters()` và các phương thức của `Element`.

Lưu ý: `TypeMirror` trả lời **“kiểu là gì?”**, còn `Element` trả lời **“khai báo nào đang được mô tả?”**. Ví dụ `VariableElement` đại diện cho field `code`; `field.asType()` đại diện cho kiểu `java.lang.String` của field đó. Hai thứ liên quan nhưng không thay thế nhau.

## 3. `TypeElement`: khai báo kiểu, không chỉ class

`TypeElement` nằm trong `javax.lang.model.element`. Nó đại diện cho một **khai báo kiểu** trong mô hình của compiler, gồm class, interface, enum, annotation type và record; nó cũng có thể biểu diễn các kiểu được cung cấp từ class file khi compiler biết về chúng.

Ví dụ:

```java
class Customer {}

interface Repository {}

enum Status { NEW, DONE }

@interface Audited {
    String value();
}

record Point(int x, int y) {}
```

Các khai báo đó đều có thể được biểu diễn bằng `TypeElement`, nhưng `getKind()` sẽ phân biệt:

| Khai báo | `ElementKind` điển hình |
| --- | --- |
| `class Customer` | `CLASS` |
| `interface Repository` | `INTERFACE` |
| `enum Status` | `ENUM` |
| `@interface Audited` | `ANNOTATION_TYPE` |
| `record Point(...)` | `RECORD` |

Một vài API chuyên biệt:

- `type.getQualifiedName()`: tên đủ điều kiện như `lesson.Invoice`. Với kiểu thành viên có tên, tên đủ điều kiện phản ánh quan hệ khai báo.
- `type.getSimpleName()`: tên ngắn như `Invoice`.
- `type.getSuperclass()`: biểu diễn `TypeMirror` của superclass khi có ý nghĩa.
- `type.getInterfaces()`: danh sách kiểu interface được implements/extends.
- `type.getTypeParameters()`: các tham số kiểu khi khai báo generic, dưới dạng `TypeParameterElement`.
- `type.getEnclosedElements()`: các khai báo trực tiếp bên trong, gồm field, constructor, method và kiểu lồng nhau tùy khai báo.

`TypeElement` **không phải** `java.lang.Class<?>`. Processor có thể xem mã nguồn chưa được biên dịch thành `.class`, trong khi `Class<?>` là đại diện runtime của một kiểu đã được JVM biết đến.

### `TypeElement` và annotation type

Khai báo `@interface Marker { String value(); }` cũng là một `TypeElement` có `ElementKind.ANNOTATION_TYPE`. Nhưng phần tử `value()` **bên trong** lại là `ExecutableElement` có `ElementKind.METHOD`.

Đây là phân biệt rất quan trọng cho processor: **loại annotation** là một khai báo kiểu; **phương thức phần tử annotation** là một khai báo phương thức thuộc kiểu đó. Nếu phần tử có `default`, processor có thể hỏi `ExecutableElement.getDefaultValue()` để lấy `AnnotationValue` tương ứng.

## 4. `ExecutableElement`: method, constructor và phần tử annotation

`ExecutableElement` biểu diễn một khai báo có dạng executable. Đối với mã Java thông thường, hai trường hợp xuất hiện nhiều nhất là:

- `ElementKind.METHOD`: khai báo phương thức.
- `ElementKind.CONSTRUCTOR`: khai báo constructor.

Ngoài ra, các phần tử khai báo bên trong annotation type như `String value();` cũng thuộc nhóm phương thức, và mô hình ngôn ngữ có thể biểu diễn những phần tử thực thi đặc biệt khác tùy cấu trúc chương trình.

Các phương thức chuyên biệt đáng dùng:

| API | Ý nghĩa |
| --- | --- |
| `getParameters()` | Danh sách `VariableElement` biểu diễn các **tham số hình thức**, theo thứ tự |
| `getReturnType()` | `TypeMirror` của kiểu trả về; với constructor hoặc method `void`, có biểu diễn giả kiểu `VOID` |
| `getTypeParameters()` | Các `TypeParameterElement` khai báo cho phương thức generic |
| `getThrownTypes()` | Các kiểu ngoại lệ được khai báo ở `throws` |
| `isVarArgs()` | Kiểm tra method/constructor có tham số biến thiên không |
| `getDefaultValue()` | Giá trị mặc định của **phần tử annotation**, nếu có; nếu không thì `null` |
| `getReceiverType()` | Kiểu của receiver nếu phù hợp với executable |
| `getSimpleName()` | Tên đơn giản của executable; nên dùng `getKind()` để phân biệt constructor với method |

Ví dụ:

```java
class MathService {
    int sum(int left, int right) {
        return left + right;
    }

    public <T> T echo(T value) {
        return value;
    }
}
```

- `sum` và `echo` là `ExecutableElement` thuộc kind `METHOD`.
- `sum.getParameters()` (trong processor khi `sum` là biến `ExecutableElement`) có hai `VariableElement` với tên `left` và `right`.
- `echo.getTypeParameters()` có một `TypeParameterElement` đại diện cho `T`.
- `sum.getReturnType()` biểu diễn kiểu nguyên thủy `int`.

**Không nhầm `getReturnType()` với thực thi phương thức.** Nó trả về thông tin **kiểu trả về của khai báo**, không chạy `sum` và không lấy một giá trị tính toán nào.

### Constructor không giống method thường

Constructor có `ElementKind.CONSTRUCTOR`, không trả kết quả nghiệp vụ. Dù cấu trúc mô hình cùng dùng `ExecutableElement`, compiler phân biệt với `METHOD`. Vì vậy, khi quét `getEnclosedElements()`, hãy kiểm tra kind hoặc dùng `ElementFilter.constructorsIn(...)` và `ElementFilter.methodsIn(...)` để không nhầm hai nhóm.

### Đọc mặc định của annotation element

```java
@interface Endpoint {
    String path();
    int timeout() default 3000;
}
```

Trong mô hình ngôn ngữ:

- `Endpoint` là `TypeElement`.
- `path()` và `timeout()` là `ExecutableElement`.
- `timeout.getDefaultValue()` trả một `AnnotationValue` đại diện cho số nguyên `3000`.
- `path.getDefaultValue()` trả `null` vì phần tử không có mặc định.

Đây là **API compile-time**. Đừng nhầm với `java.lang.reflect.Method.getDefaultValue()` ở runtime; tên API giống nhau nhưng kiểu dữ liệu và môi trường làm việc khác nhau.

## 5. `VariableElement`: field, tham số và nhiều loại biến

`VariableElement` là interface dùng cho khai báo biến trong mô hình compiler. Nó không chỉ đại diện cho **field của class**.

| Mã khai báo | `ElementKind` | Phần tử tương ứng |
| --- | --- | --- |
| `private String code;` trong class | `FIELD` | `VariableElement` của field `code` |
| `void run(int count)` | `PARAMETER` | `VariableElement` của parameter `count` |
| `enum Stage { NEW }` | `ENUM_CONSTANT` | `VariableElement` của hằng `NEW` |
| `int n = 5;` trong phương thức | `LOCAL_VARIABLE` khi mô hình có phần tử đó | `VariableElement` của biến cục bộ |
| `catch (Exception ex)` | `EXCEPTION_PARAMETER` khi mô hình có phần tử đó | `VariableElement` của `ex` |

Một số kind khác liên quan biến còn có thể gặp trong mô hình ngôn ngữ. Điều thiết yếu là **đọc `getKind()` trước khi kết luận một `VariableElement` là field hay parameter**.

Các API thường dùng:

- `variable.getSimpleName()`: tên khai báo, ví dụ `quantity`.
- `variable.asType()`: `TypeMirror` biểu diễn kiểu, ví dụ `int`.
- `variable.getEnclosingElement()`: phần tử bao ngoài trực tiếp — method cho parameter, class cho field.
- `variable.getConstantValue()`: trả giá trị compile-time constant cho một **field `static final` kiểu nguyên thủy hoặc `String`** thỏa điều kiện constant variable; các biến khác trả `null`. Không dùng API này để “đọc giá trị hiện tại” của object.

### Tên trùng không đồng nghĩa cùng `VariableElement`

```java
class Parcel {
    private String label;

    void rename(String label) {
        this.label = label;
    }
}
```

Ở đây có hai khai báo cùng tên `label`:

1. `Parcel.label` là field → `VariableElement` kind `FIELD`.
2. Tham số `label` của `rename` là parameter → `VariableElement` kind `PARAMETER`.

Processor phân biệt chúng qua `getKind()` và `getEnclosingElement()`. Nếu muốn liệt kê field của class, dùng `ElementFilter.fieldsIn(type.getEnclosedElements())`; nếu muốn liệt kê parameter của một method, dùng `executable.getParameters()`.

### Biến cục bộ không mặc nhiên xuất hiện trong `getEnclosedElements()`

Mô hình annotation processing thường phục vụ khai báo ở mức type, member và parameter. **Không nên giả định** duyệt `TypeElement.getEnclosedElements()` sẽ tìm được mọi biến cục bộ trong thân method. Nếu yêu cầu phân tích biểu thức và câu lệnh chi tiết bên trong thân, hãy dùng API cây cú pháp của compiler như `com.sun.source.tree` / `com.sun.source.util.Trees` khi môi trường hỗ trợ, không xem `Element` là AST đầy đủ.

## 6. Ví dụ Java 17+ đầy đủ: annotation processor duyệt cả ba loại phần tử

Để chứng minh đúng vai trò của API **compile-time**, ví dụ dùng hai tệp Java trong thư mục `lesson`. Ta tạo một annotation `@Inspect` giữ ở source và processor riêng, sau đó biên dịch một lớp `Invoice` có annotation đó. Processor sẽ in thông tin mà compiler cung cấp trước khi chạy chương trình.

Cấu trúc thư mục:

```text
project/
└── lesson/
    ├── InspectProcessor.java
    └── Invoice.java
```

### Tệp 1 — `lesson/InspectProcessor.java`

```java
package lesson;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.ElementFilter;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface Inspect {}

@SupportedAnnotationTypes("lesson.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class InspectProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Inspect.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            System.out.println("TYPE "
                    + type.getQualifiedName()
                    + " kind=" + type.getKind());

            for (VariableElement field :
                    ElementFilter.fieldsIn(type.getEnclosedElements())) {
                System.out.println("FIELD "
                        + field.getSimpleName()
                        + " type=" + field.asType());
            }

            for (ExecutableElement ctor :
                    ElementFilter.constructorsIn(type.getEnclosedElements())) {
                System.out.println("CONSTRUCTOR parameters="
                        + ctor.getParameters().size());
            }

            for (ExecutableElement method :
                    ElementFilter.methodsIn(type.getEnclosedElements())) {

                System.out.println("METHOD "
                        + method.getSimpleName()
                        + " returns=" + method.getReturnType());

                for (VariableElement parameter : method.getParameters()) {
                    System.out.println("PARAMETER "
                            + parameter.getSimpleName()
                            + " type=" + parameter.asType());
                }
            }
        }

        return true;
    }
}
```

Giải thích:

- `@SupportedAnnotationTypes("lesson.Inspect")` chỉ định loại annotation mà processor xử lý.
- `@SupportedSourceVersion(RELEASE_17)` công bố phiên bản ngôn ngữ được hỗ trợ.
- `roundEnv.getElementsAnnotatedWith(Inspect.class)` trả các `Element` được gắn trực tiếp bằng `@Inspect` trong vòng xử lý phù hợp.
- Kiểm tra `instanceof TypeElement` để chỉ xử lý khai báo kiểu.
- `ElementFilter.fieldsIn(...)`, `constructorsIn(...)`, `methodsIn(...)` lọc các phần tử theo loại, tránh ép kiểu bừa bãi.
- `getParameters()` trả các `VariableElement` của method hoặc constructor.
- Trả `true` nghĩa là processor đã claim annotation mà mình hỗ trợ trong vòng xử lý này. Trạng thái `processingOver()` ngăn in thêm dữ liệu khi vòng xử lý kết thúc.

`@Retention(SOURCE)` đủ cho processor hoạt động vì nó chạy khi biên dịch. Không phải dùng `RUNTIME` để đọc annotation bằng `RoundEnvironment`.

### Tệp 2 — `lesson/Invoice.java`

```java
package lesson;

@Inspect
class Invoice {
    private final String code;

    Invoice(String code) {
        this.code = code;
    }

    int total(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
```

Trong ví dụ:

- `Invoice` → một `TypeElement` kind `CLASS`.
- `code` (field) → `VariableElement` kind `FIELD`, kiểu `java.lang.String`.
- `Invoice(String code)` → `ExecutableElement` kind `CONSTRUCTOR`, có một parameter.
- `total(int quantity, int unitPrice)` → `ExecutableElement` kind `METHOD`, kiểu trả về `int`.
- `quantity` và `unitPrice` → hai `VariableElement` kind `PARAMETER`, cùng kiểu `int`.

### Biên dịch và kết quả

Chạy các lệnh sau từ thư mục `project` (cha của thư mục `lesson`). JDK 17 hoặc mới hơn, dùng `--release 17` để thống nhất với `RELEASE_17`:

```bash
javac --release 17 -encoding UTF-8 lesson/InspectProcessor.java
javac --release 17 -encoding UTF-8 -cp . -processorpath . -processor lesson.InspectProcessor lesson/Invoice.java
```

Lệnh đầu biên dịch processor và annotation `Inspect`. Lệnh thứ hai khởi động processor tường minh bằng `-processor lesson.InspectProcessor` rồi biên dịch `Invoice`. Chương trình **không có `main`** vì mục đích là quan sát output của annotation processor ở **giai đoạn biên dịch**.

**Những dòng in bởi processor (stdout của bước biên dịch thứ hai):**

```text
TYPE lesson.Invoice kind=CLASS
FIELD code type=java.lang.String
CONSTRUCTOR parameters=1
METHOD total returns=int
PARAMETER quantity type=int
PARAMETER unitPrice type=int
```

Output trên không phụ thuộc vào việc chạy `java lesson.Invoice` (lớp `Invoice` không có `main`). Đây là các lệnh in từ phương thức `process(...)` khi compiler duyệt mô hình khai báo.

Sắp xếp output ổn định vì processor chủ động in thành ba nhóm riêng: các field, các constructor và các method. Trong mỗi nhóm ở ví dụ chỉ có một khai báo, còn method chỉ có hai tham số theo thứ tự. Với class lớn, nếu cần order độc lập với trình biên dịch/nguồn, hãy chủ động sắp xếp danh sách phần tử theo tiêu chí rõ ràng.

### Đi từng bước trong processor

1. Compiler nhận ra `@Inspect` trên `Invoice` và cung cấp `Element` tương ứng qua `RoundEnvironment`.
2. `element instanceof TypeElement` xác nhận ứng viên là **khai báo kiểu**.
3. `type.getQualifiedName()` in `lesson.Invoice` và `type.getKind()` in `CLASS`.
4. `ElementFilter.fieldsIn(...)` giữ field `code`; `field.asType()` in `java.lang.String`.
5. `ElementFilter.constructorsIn(...)` lấy constructor khai báo tường minh, có đúng một parameter `code`.
6. `ElementFilter.methodsIn(...)` lấy method `total`; `getReturnType()` là `int`.
7. `method.getParameters()` trả `quantity`, `unitPrice`, cũng là các `VariableElement`; `asType()` tương ứng trả `int`.

Nếu bỏ `@Inspect` khỏi `Invoice`, processor vẫn có thể được gọi do khai báo `-processor`, nhưng `roundEnv.getElementsAnnotatedWith(Inspect.class)` sẽ không còn chứa `Invoice`. Trong cấu hình processor cụ thể, không thể suy từ việc “processor được đăng ký” rằng mỗi class đều là mục tiêu: **tập phần tử được gắn annotation và chính sách chọn ứng viên là hai điều phải phân biệt**.

## 7. Chọn đúng API từ mục tiêu cần phân tích

Giả sử bạn viết một công cụ kiểm tra: “Mọi method có `@Endpoint` phải có tham số `requestId` kiểu `String`”. Một cách tiếp cận phù hợp trong annotation processing là:

1. Lấy các phần tử được gắn `@Endpoint` từ `RoundEnvironment`.
2. Kiểm tra `getKind() == ElementKind.METHOD` trước khi ép sang `ExecutableElement`.
3. Duyệt `ExecutableElement.getParameters()`.
4. Với từng `VariableElement`, đọc `getSimpleName()` và `asType()`.
5. Nếu vi phạm, gửi diagnostic gắn đúng phần tử bằng `processingEnv.getMessager().printMessage(...)`.

Nếu phải phân biệt hai kiểu Java **theo ngữ nghĩa** (ví dụ generic, assignability, subtype), đừng chỉ so sánh chuỗi `typeMirror.toString()`. Hãy dùng `Types.isSameType(...)`, `Types.isAssignable(...)` hoặc các hàm thích hợp ở `processingEnv.getTypeUtils()`. Tên kiểu hiển thị bằng chuỗi rất hữu ích cho bài học, nhưng không phải luôn là bộ so sánh kiểu đáng tin trong processor thực tế.

### `Elements`, `Types`, `ElementFilter` khác nhau thế nào?

| Công cụ | Chức năng chính | Tình huống sử dụng |
| --- | --- | --- |
| `Elements` | Tra cứu và hỗ trợ làm việc với các khai báo `Element` | Tìm một `TypeElement` bằng tên, lấy package hoặc thông tin tài liệu |
| `Types` | Phân tích và so sánh `TypeMirror` | Kiểm tra kiểu gán được, quan hệ subtype, chuyển đổi kiểu |
| `ElementFilter` | Lọc collection `Element` thành các nhóm chuyên biệt | Lấy field, method, constructor từ `getEnclosedElements()` |

Những API này bổ sung cho nhau. `TypeElement` chỉ ra **đối tượng khai báo**, `TypeMirror` biểu diễn **kiểu**, còn `Elements`/`Types` là **công cụ hỗ trợ truy vấn**.

## 8. AnnotationMirror và giá trị phần tử trong compile-time

Trong module Java annotation, ngoài việc biết class/method/field nào đang được đánh dấu, processor còn cần đọc **các giá trị của annotation**. `Element.getAnnotationMirrors()` cung cấp các `AnnotationMirror` mô tả annotation trực tiếp trên phần tử.

Có thể dùng:

- `AnnotationMirror.getAnnotationType()` để biết loại annotation.
- `AnnotationMirror.getElementValues()` để nhận map từ `ExecutableElement` (tên phần tử annotation) sang `AnnotationValue`, với các giá trị được nêu tường minh tại nơi sử dụng.
- `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` để lấy các giá trị **bao gồm mặc định** của những phần tử annotation.

Ví dụ ý niệm:

```java
@interface Policy {
    int retries() default 2;
}

@Policy
class Example {}
```

Trong compiler, `retries()` của annotation `Policy` là **`ExecutableElement`**; default `2` có thể đọc qua `getDefaultValue()` của executable đó. `AnnotationMirror.getElementValues()` đối với `@Policy` trên `Example` không có giá trị `retries` tường minh, nhưng `Elements.getElementValuesWithDefaults(...)` có thể cung cấp giá trị `2`.

**Lưu ý:** `ExecutableElement.getDefaultValue()` nói về **định nghĩa phần tử**, còn `Elements.getElementValuesWithDefaults(...)` nói về **cách sử dụng một annotation cụ thể sau khi tính cả default**.

Đây là thao tác trên **mô hình biên dịch**, khác với `java.lang.reflect.Method` và proxy annotation đọc lúc runtime. Processor không cần `@Retention(RUNTIME)` chỉ để nhìn thấy annotation lúc biên dịch.

## 9. Những bẫy phổ biến khi viết annotation processor

### Nhầm `Element` với Reflection

`TypeElement` không phải `Class<?>`. `ExecutableElement` không phải `java.lang.reflect.Method`. `VariableElement` không phải `java.lang.reflect.Field`. Processor kiểm tra mô hình nguồn/biên dịch, nên tránh tải class đang biên dịch bằng `Class.forName(...)` để thay thế — có thể class ấy chưa tồn tại hoặc là phiên bản cũ trên classpath.

### Ép mọi `Element` sang `TypeElement`

`RoundEnvironment.getElementsAnnotatedWith(...)` trả các loại `Element` phù hợp với annotation và target. Annotation có thể gắn lên method, field hoặc parameter. Nếu luôn ép thành `TypeElement`, processor dễ gây `ClassCastException`. Cần kiểm tra `ElementKind` hoặc dùng `instanceof`.

### Xem `VariableElement` chỉ là field

Tham số method/constructor cũng là `VariableElement`, và enum constant thuộc nhóm này. Dùng `getKind()` và `getEnclosingElement()` để phân biệt.

### Xem constructor là method thông thường

Cả hai đều được mô tả bởi `ExecutableElement` nhưng `getKind()` khác nhau. Nếu chỉ muốn xử lý method, dùng `ElementFilter.methodsIn(...)` thay vì xử lý cả constructor.

### Xem `getEnclosedElements()` là toàn bộ cây AST

API này mô tả **các khai báo được bao trong phần tử**, không phải mọi câu lệnh và biểu thức bên trong thân method. Với biến cục bộ và nội dung thân method, cần công cụ AST phù hợp.

### So sánh `TypeMirror` bằng chuỗi

`toString()` rất hữu ích để hiển thị, nhưng kiểm tra kiểu cần tính cả generic, wildcard, boxing, subtype hoặc lỗi kiểu đang biên dịch; sử dụng `Types` thay vì chỉ so chuỗi.

### Quên nhiều vòng xử lý

Annotation processing có thể chạy qua nhiều **round** khi processor sinh thêm source. `process(...)` có thể được gọi nhiều lần. Hãy chú ý `roundEnv.processingOver()`, `roundEnv.errorRaised()` và tránh in/sinh cùng một tệp nhiều lần khi thiết kế processor thực tế.

### Quên `SOURCE` vẫn xử lý được lúc biên dịch

`@Retention(SOURCE)` không làm annotation vô hình đối với processor ở giai đoạn biên dịch. Retention chỉ quyết định metadata còn lại đến bytecode/runtime hay không.

### Chọn không đúng phần tử để báo lỗi

Nếu rule sai ở tham số `quantity`, nên phát diagnostic gắn vào `VariableElement` đó; nếu lỗi thuộc cả khai báo class thì gắn vào `TypeElement`. Việc xác định đúng loại phần tử giúp compiler/IDE báo lỗi tại vị trí rõ ràng.

## 10. Bài tập tự kiểm tra

**Câu 1.** Trong `class User { String id; }`, class và field tương ứng interface nào?

**Đáp án:** `User` là `TypeElement` (kind `CLASS`); `id` là `VariableElement` (kind `FIELD`).

**Câu 2.** Một `void save(String name)` gồm những phần tử nào?

**Đáp án:** `save` là `ExecutableElement` (kind `METHOD`), còn `name` là `VariableElement` (kind `PARAMETER`). Kiểu `String` của `name` được biểu diễn bởi `TypeMirror` từ `name.asType()`.

**Câu 3.** Khi xử lý `@interface Marker { int level() default 4; }`, `Marker` và `level()` là gì?

**Đáp án:** `Marker` là `TypeElement` (kind `ANNOTATION_TYPE`), `level()` là `ExecutableElement` (kind `METHOD`). `level.getDefaultValue()` đại diện mặc định `4`.

**Câu 4.** Vì sao đoạn `Class<?> c = Class.forName("lesson.Invoice")` không thay thế đáng tin `TypeElement` trong processor?

**Đáp án:** Processor có thể đang phân tích nguồn `Invoice` trước khi class file được biên dịch. Reflection tải một class runtime đã tồn tại trên classpath và có thể không trùng với khai báo đang xử lý.

**Câu 5.** Muốn lấy danh sách tham số của một method đã có dưới dạng `ExecutableElement` thì gọi gì?

**Đáp án:** `method.getParameters()`; các kết quả là `VariableElement` và giữ thứ tự tham số hình thức.

**Câu 6.** Vì sao `getDeclaredMethods()` trên `Class<?>` không phải phương án chuẩn để liệt kê các method đang được processor biên dịch?

**Đáp án:** Đó là Reflection runtime. Processor phải dùng `TypeElement.getEnclosedElements()` và lọc `ElementFilter.methodsIn(...)` hoặc kiểm tra `ElementKind.METHOD`.

**Câu 7.** `VariableElement.getConstantValue()` có đọc được giá trị hiện thời của field `private int counter` trong một instance không?

**Đáp án:** Không. Nó chỉ cung cấp hằng compile-time trong điều kiện phù hợp; không truy cập trạng thái instance runtime.

**Câu 8.** Một processor muốn kiểm tra `List<String>` có thể gán cho kiểu khác không. Nên chọn `Elements` hay `Types`?

**Đáp án:** `Types` với các hàm so sánh/assignability trên `TypeMirror` phù hợp. `Elements` phục vụ khai báo và tiện ích liên quan phần tử.

**Câu 9.** `@Retention(SOURCE)` có làm `roundEnv.getElementsAnnotatedWith(Inspect.class)` không tìm được lớp `Invoice` trong lúc biên dịch không?

**Đáp án:** Không. Processor hoạt động ở compile-time nên annotation SOURCE vẫn có thể được quan sát, miễn processor được đăng ký và kiểu/đích annotation đúng.

**Câu 10.** Nếu `@Policy` không viết `retries` nhưng phần tử có `default 2`, API compile-time nào lấy đủ default?

**Đáp án:** `Elements.getElementValuesWithDefaults(annotationMirror)`. Còn `ExecutableElement.getDefaultValue()` đọc trực tiếp default của phần tử `retries()` trong định nghĩa loại annotation.

## 11. Quy tắc ghi nhớ

**`TypeElement` = khai báo kiểu; `ExecutableElement` = khai báo thực thi (method/constructor/phần tử annotation); `VariableElement` = khai báo biến (field/parameter/enum constant...).** Ba loại cùng thuộc `javax.lang.model.element`, được compiler cấp cho annotation processor. Sử dụng `ElementKind` để xác minh loại phần tử, `getEnclosedElements()` để đi qua cấu trúc khai báo, `getParameters()` cho tham số, `asType()`/`TypeMirror` cho thông tin kiểu và `ElementFilter` để lọc an toàn.

Khi chuyển từ **biên dịch** sang **runtime**, hãy chuyển đúng mô hình tư duy: Java Reflection dùng `Class`, `Method`, `Field` để kiểm tra lớp đã có; nó không thay thế các interface của `javax.lang.model` trong annotation processing.
