# Mô hình khai báo Java: AnnotationMirror và AnnotationValue

## Mục tiêu bài học

Trong **annotation processing**, processor cần đọc annotation đang có trên class, interface, method hoặc một khai báo khác **trong lúc compiler chưa tạo xong bytecode**. Hai API nền tảng giải quyết việc này là **javax.lang.model.element.AnnotationMirror** (mô tả một annotation đang hiện diện) và **javax.lang.model.element.AnnotationValue** (mô tả giá trị của một phần tử trong annotation).

Sau bài này, bạn có thể:

1. Hiểu cách tìm annotation qua **Element.getAnnotationMirrors()**, đọc type của annotation và ánh xạ từ phương thức khai báo annotation đến giá trị.
2. Phân biệt **giá trị ghi tường minh** với **giá trị mặc định** bằng **AnnotationMirror.getElementValues()** và **Elements.getElementValuesWithDefaults(...)**.
3. Giải thích vì sao key của map là **ExecutableElement** và value là **AnnotationValue**, không phải đơn thuần Map<String, Object>.
4. Xử lý đúng sáu nhóm giá trị annotation: primitive wrapper, String, **TypeMirror** cho class literal, **VariableElement** cho enum constant, **AnnotationMirror** cho annotation lồng nhau và **List<? extends AnnotationValue>** cho array.
5. Dùng **AnnotationValueVisitor** / **SimpleAnnotationValueVisitor9** để đọc dữ liệu mà không ép kiểu sai; hiểu hạn chế của việc chuyển thẳng annotation sang proxy runtime.
6. Viết, biên dịch và chạy một annotation processor Java 17+ ghi bảng giá trị annotation ra resource, có output và lệnh javac rõ ràng.

**Phạm vi:** API chuẩn trong module **java.compiler** còn áp dụng trên các JDK hiện đại. Ví dụ dùng **JDK 17+**, được kiểm chứng bằng **OpenJDK 24.0.2 với --release 17**. Không cần bất kỳ thư viện bên ngoài hoặc cơ chế annotation processing lỗi thời nào.

## 1. Annotation là khai báo, không phải một đối tượng runtime bắt buộc

Ví dụ một class dùng annotation cấu hình:

~~~java
@Policy(
    label = "billing",
    handler = java.util.ArrayList.class,
    level = Policy.Level.HIGH)
public final class Job {}
~~~

Ở compile time, processor có thể phân tích:

- Annotation có tên **demo.model.Policy** đang hiện diện trên **demo.app.Job**.
- Những element được viết trực tiếp: **label**, **handler**, **level**.
- Những element dùng default: **meta** và **retries**.
- **handler** là class literal, nhưng class tham chiếu không nhất thiết được nạp vào JVM của processor.
- **level** là enum constant, nhưng mục tiêu của processor là mô hình khai báo, không phải thực thi logic ứng dụng.

Quan hệ giữa các đối tượng:

~~~text
Element (demo.app.Job)
    │
    └── getAnnotationMirrors()
            │
            ▼
      AnnotationMirror (@demo.model.Policy)
            │
            ├── getAnnotationType(): DeclaredType
            │
            ├── getElementValues():
            │      Map<ExecutableElement, AnnotationValue>
            │      chỉ các element có giá trị tường minh
            │
            └── Elements.getElementValuesWithDefaults(...)
                   cũng trả những element dùng default
                           │
                           ▼
                    AnnotationValue
                           │
                           └── accept(AnnotationValueVisitor)
~~~

Không đánh đồng **AnnotationMirror** với **java.lang.annotation.Annotation**. Đối tượng thứ nhất thuộc mô hình biên dịch; đối tượng thứ hai thường được dùng qua reflection hoặc proxy annotation trong runtime.

## 2. AnnotationMirror: đại diện của annotation

**javax.lang.model.element.AnnotationMirror** đại diện cho một annotation gắn trên một đối tượng thuộc mô hình ngôn ngữ. Các phương thức trực tiếp:

| API | Giá trị trả về | Công dụng |
| --- | --- | --- |
| **getAnnotationType()** | **DeclaredType** | Type của annotation, ví dụ demo.model.Policy |
| **getElementValues()** | **Map<? extends ExecutableElement, ? extends AnnotationValue>** | Chỉ các element mà người viết annotation đã cung cấp giá trị tường minh |

Thông thường, bạn bắt đầu từ **Element.getAnnotationMirrors()**, rồi xác định annotation mong muốn qua **getAnnotationType().asElement()**:

~~~java
// Mảnh minh họa dùng bên trong annotation processor; không chạy độc lập.
for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    TypeElement annotationType =
            (TypeElement) mirror.getAnnotationType().asElement();

    if (annotationType.getQualifiedName()
            .contentEquals("demo.model.Policy")) {
        // Đây là @demo.model.Policy.
    }
}
~~~

**getAnnotationType()** trả về **DeclaredType**, không phải **Class<?>**. Dùng **TypeElement.getQualifiedName()** hoặc công cụ của **Elements/Types** để xác định đúng tên thay vì nạp class bằng **Class.forName**.

### 2.1. Annotation trực tiếp và annotation kế thừa

**Element.getAnnotationMirrors()** cho bạn các annotation hiện diện **trực tiếp** trên construct theo mô hình Element. Nếu xử lý annotation của một class kế thừa, cần phân biệt điều này với cách Java xử lý **@Inherited**.

API **Elements.getAllAnnotationMirrors(element)** có thể trả cả những annotation được xem là hiện diện thông qua kế thừa theo ngữ nghĩa hỗ trợ của mô hình ngôn ngữ. Không tùy tiện thay hai API cho nhau: processor phải quyết định cần **khai báo trực tiếp** hay **effective annotation từ hierarchy**. Ngoài ra, annotation khai báo và **type-use annotation** có vị trí/phạm vi khác nhau; khi cần type annotations, phải chọn đúng đối tượng **AnnotatedConstruct/TypeMirror** để kiểm tra.

### 2.2. Annotation lặp lại

Với annotation đánh dấu **@Repeatable**, trên source có thể xuất hiện nhiều annotation cùng loại, và compiler có thể biểu diễn chúng qua **container annotation** tùy ngữ cảnh. Đừng giả định tìm được đúng một AnnotationMirror theo simple name là luôn đủ. Nếu yêu cầu hỗ trợ repeated annotations, phải xem contract của annotation và API phù hợp, rồi xử lý cả trường hợp container.

Ví dụ hoàn chỉnh trong bài chỉ dùng **một annotation @Policy** trên một class, không dùng @Repeatable, để giữ trọng tâm ở dữ liệu AnnotationValue.

### 2.3. Đừng dựa vào danh tính object

Hai đối tượng mirror có thể cùng biểu diễn annotation tương ứng nhưng không có yêu cầu chúng phải là cùng một object reference. Nếu cần so sánh mirror, tuân thủ contract **equals(...)**; nếu cần xác định loại annotation, so sánh danh tính type/qualified name theo mô hình ngôn ngữ. Không dùng **==** giữa hai AnnotationMirror làm điều kiện nghiệp vụ.

## 3. Key là ExecutableElement: tại sao không phải String?

Trong Java, một annotation interface được định nghĩa bằng các phương thức không tham số; mỗi phương thức là một **annotation element**:

~~~java
public @interface Policy {
    String label();
    Class<?> handler() default String.class;
    int[] retries() default {1, 3};
}
~~~

Như vậy, **label()**, **handler()**, **retries()** được mô hình ngôn ngữ biểu diễn thành **ExecutableElement**. Map từ AnnotationMirror giữ key là declaration element chứ không chỉ tên chuỗi, giúp processor xem thêm type, return type, default và vị trí khai báo của annotation element.

Ví dụ truy cập:

~~~java
// Mảnh code minh họa.
Map<? extends ExecutableElement, ? extends AnnotationValue> values =
        mirror.getElementValues();

for (var entry : values.entrySet()) {
    ExecutableElement method = entry.getKey();
    AnnotationValue value = entry.getValue();

    String name = method.getSimpleName().toString();
    TypeMirror declaredReturnType = method.getReturnType();

    // Sử dụng name, declaredReturnType và value theo bài toán của processor.
}
~~~

Ở đoạn này:

- **method.getSimpleName()** trả tên element, ví dụ **label**.
- **method.getReturnType()** trả kiểu khai báo của element (như String hoặc int[]).
- **method.getDefaultValue()** trả giá trị mặc định dạng **AnnotationValue** nếu element có khai báo default, hoặc **null** nếu không có.
- **entry.getValue()** là giá trị hiệu lực của entry map tương ứng; với **getElementValues()**, chỉ có những element được ghi tường minh.

Không dùng **method.getReturnType()** để thay thế việc đọc **AnnotationValue**: return type mô tả dạng dữ liệu cho phép, không mô tả giá trị người dùng đã cung cấp.

## 4. Giá trị tường minh và giá trị mặc định

Đây là điểm quan trọng nhất của bài.

Giả sử annotation định nghĩa:

~~~java
public @interface Policy {
    String label();
    Class<?> handler() default String.class;
    Level level() default Level.NORMAL;
    int[] retries() default {1, 3};
}
~~~

Và source viết:

~~~java
@Policy(label = "billing", handler = java.util.ArrayList.class)
public final class Job {}
~~~

Khi đó:

| Phương thức | Có trong getElementValues()? | Giá trị hiệu lực khi có defaults |
| --- | --- | --- |
| **label()** | Có | "billing" |
| **handler()** | Có | java.util.ArrayList.class |
| **level()** | Không | Level.NORMAL |
| **retries()** | Không | {1, 3} |

**AnnotationMirror.getElementValues()** trả **chỉ những phần tử được viết tường minh trong annotation**. Việc một element có default không làm nó tự xuất hiện trong map này. Nếu source viết **level = Level.NORMAL**, element level sẽ có mặt dù giá trị bằng default.

Muốn lấy cả những element dùng default, gọi:

~~~java
// Mảnh mã minh họa; elements lấy từ processingEnv.getElementUtils().
Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();

Map<? extends ExecutableElement, ? extends AnnotationValue> effective =
        processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
~~~

**getElementValuesWithDefaults(...)** là API trong **javax.lang.model.util.Elements**, **không phải** phương thức của chính AnnotationMirror.

### 4.1. Khi nào nên chọn cách nào?

- **Công cụ kiểm tra chính sách:** Nếu muốn biết người dùng có **chủ động ghi** một tùy chọn hay không, dùng **getElementValues()**.
- **Code generator:** Nếu cần giá trị áp dụng sau khi xét default, dùng **getElementValuesWithDefaults()**.
- **Linter:** Đôi khi cần cả hai để phát hiện cấu hình dư thừa, ví dụ người dùng ghi tường minh một giá trị bằng default.
- **Serializer metadata:** Cần quyết định sản phẩm xuất đúng source intent hay xuất effective configuration; không nên chuyển qua lại mà không nêu rõ.

Đừng giả định thứ tự iteration của map chính là thứ tự dùng để serialize ổn định. API có thông tin về thứ tự value được ghi trong source, nhưng khi tạo output có hợp đồng nhất quán, hãy sắp xếp theo **tên element** như ví dụ đầy đủ.

### 4.2. Trường hợp annotation không có element

Một **marker annotation**, chẳng hạn **@Enabled** với khai báo **public @interface Enabled {}**, không có element nào để ánh xạ. Vì vậy **getElementValues()** trả map rỗng. Map rỗng **không có nghĩa annotation vắng mặt**: sự hiện diện được xác định từ **AnnotationMirror** của element.

## 5. AnnotationValue là gì?

**javax.lang.model.element.AnnotationValue** đại diện một giá trị annotation element. Các phương thức chính:

| API | Ý nghĩa |
| --- | --- |
| **getValue()** | Lấy biểu diễn Java object thuộc một trong các nhóm giá trị của mô hình |
| **accept(AnnotationValueVisitor<R,P>, P)** | Gọi visitor phù hợp với loại giá trị |
| **toString()** | Biểu diễn giá trị ở dạng thích hợp để mô tả annotation như source Java |

### 5.1. Các loại giá trị thực tế

Theo contract của AnnotationValue, **getValue()** có thể trả:

| Annotation element khai báo | Dạng mà getValue() trả | Ví dụ |
| --- | --- | --- |
| Primitive như int, boolean | Wrapper tương ứng, ví dụ Integer, Boolean | retries array có phần tử Integer |
| **String** | java.lang.String | label="billing" |
| **Class<?> / Class<?>[]** | **TypeMirror** cho từng class literal | java.util.ArrayList.class |
| **Enum** | **VariableElement** của enum constant | Policy.Level.HIGH |
| Annotation lồng nhau | **AnnotationMirror** | @Policy.Meta(code="fallback") |
| Array của các dạng hỗ trợ | **List<? extends AnnotationValue>** | {1, 3} trở thành list hai AnnotationValue |

Đặc biệt:

- **Class literal trong annotation không được trả thành Class<?> runtime.** Nó được mô tả bằng **TypeMirror**. Khi đang biên dịch, type có thể chưa tải được bởi ClassLoader của processor.
- Enum constant được biểu diễn qua **VariableElement**; có thể lấy **getSimpleName()**, **getEnclosingElement()** hoặc kiểm tra declaration của enum khi cần.
- Một annotation lồng nhau trả tiếp **AnnotationMirror**, nên có thể đọc các element của nó bằng cùng API.
- Array của annotation values trả **List<? extends AnnotationValue>** ngay cả khi array chứa một phần tử. Với array, cần truy cập từng AnnotationValue thành viên.

Không ép kiểu tất cả giá trị thành **String**, không dùng **Class.forName(...)** cho class literals và không giả định **getValue()** của enum là chính object enum chạy trong JVM.

### 5.2. Dùng visitor để xử lý đúng theo loại

API **AnnotationValueVisitor<R,P>** cung cấp các overload như:

- **visitString(...)** cho String.
- **visitType(...)** cho TypeMirror.
- **visitEnumConstant(...)** cho VariableElement.
- **visitAnnotation(...)** cho annotation lồng nhau.
- **visitArray(...)** cho List của AnnotationValue.
- **visitInt(...)**, **visitBoolean(...)** và các method tương ứng cho primitive.

Một visitor áp dụng được bằng:

~~~java
// Mảnh minh họa.
String rendered = annotationValue.accept(printer, null);
~~~

Trong đó **printer** là implementation của **AnnotationValueVisitor<String, Void>**. **SimpleAnnotationValueVisitor9** là một lớp cơ sở có sẵn, tương thích JDK 17+, cho phép định nghĩa một **defaultAction(...)** cho loại giá trị chưa cần xử lý đặc biệt.

Cách này tránh chuỗi ép kiểu với instanceof quá dài và giúp bạn kiểm soát chính xác cách hiển thị class literal, enum, nested annotation và array.

## 6. AnnotationValue.toString() và visitor: chọn công cụ nào?

**AnnotationValue.toString()** cung cấp cách biểu diễn tương tự cú pháp annotation Java; nó tiện cho diagnostic hoặc xem nhanh khi debug. Nhưng một công cụ xuất metadata thường cần định dạng chính xác, thứ tự key, escaping, cách biểu diễn nested annotation và schema output rõ ràng.

Vì vậy:

- Dùng **toString()** khi muốn xem giá trị phù hợp cho chẩn đoán.
- Dùng **getValue()** nếu code kiểm tra một loại giá trị đã được xác định đúng theo contract, rồi xử lý kiểu tương ứng.
- Dùng **visitor** nếu processor cần hỗ trợ nhiều nhóm giá trị, đặc biệt nested annotation/arrays, và muốn tự điều khiển định dạng output.
- Dùng **Elements.getElementValuesWithDefaults(...)** trước khi render nếu cần effective values.

**Lưu ý định dạng:** Visitor mẫu trong bài chỉ escape dấu **\\** và dấu nháy trong String để cho output dễ quan sát. Nếu serialize các chuỗi annotation tùy ý có newline, tab, ký tự điều khiển hoặc Unicode escaping yêu cầu riêng, phải mở rộng logic escaping và định nghĩa schema một cách đầy đủ. Bài mẫu dùng các String cố định và đã kiểm thử chính xác.

## 7. Ví dụ chạy được trên JDK 17+: đọc mirror, defaults và mọi nhóm giá trị

Chúng ta tạo:

- **@Policy**: annotation với String bắt buộc, class literal, enum, annotation lồng nhau, int array có default.
- **PolicyProcessor**: dùng AnnotationMirror và AnnotationValueVisitor để tạo một resource text trên mỗi class được annotate.
- **Job**: chỉ định ba giá trị, để hai giá trị dùng defaults.
- **Main**: đọc và in resource được tạo trong quá trình biên dịch.

Tất cả hoạt động với Java compiler chuẩn, không cần framework.

### 7.1. Cấu trúc dự án

~~~text
annotation-mirror-demo/
└── src/
    └── demo/
        ├── model/Policy.java
        ├── processor/PolicyProcessor.java
        └── app/
            ├── Job.java
            └── Main.java
~~~

### 7.2. Định nghĩa annotation: src/demo/model/Policy.java

~~~java
package demo.model;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Policy {
    String label();
    Class<?> handler() default String.class;
    Level level() default Level.NORMAL;
    Meta meta() default @Meta(code = "fallback");
    int[] retries() default {1, 3};

    enum Level { NORMAL, HIGH }

    @interface Meta {
        String code();
    }
}
~~~

**Những điều cần chú ý:**

- **label()** không có default nên class sử dụng annotation phải truyền giá trị.
- **handler()** khai báo Class, nhưng processor sẽ đọc **TypeMirror**.
- **level()** dùng enum nested **Policy.Level**, processor sẽ đọc **VariableElement**.
- **meta()** dùng annotation nested **Policy.Meta**, processor sẽ đọc **AnnotationMirror** và tiếp tục đọc **code()**.
- **retries()** là int array, processor sẽ đọc một **List<? extends AnnotationValue>**, mỗi item có giá trị Integer.
- **@Retention(SOURCE)** là phù hợp khi annotation chỉ cần tồn tại trong quá trình compile, không đòi hỏi reflection tại runtime.

### 7.3. Processor: src/demo/processor/PolicyProcessor.java

Tạo file với toàn bộ code dưới đây:

~~~java
package demo.processor;

import demo.model.Policy;
import java.io.IOException;
import java.io.Writer;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.StringJoiner;
import java.util.TreeMap;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.SimpleAnnotationValueVisitor9;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.model.Policy")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class PolicyProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }
        Elements elements = processingEnv.getElementUtils();
        Printer printer = new Printer(elements);

        for (Element element : round.getElementsAnnotatedWith(Policy.class)) {
            AnnotationMirror mirror = null;
            for (AnnotationMirror candidate : element.getAnnotationMirrors()) {
                TypeElement annotationType =
                        (TypeElement) candidate.getAnnotationType().asElement();
                if (annotationType.getQualifiedName()
                        .contentEquals("demo.model.Policy")) {
                    mirror = candidate;
                    break;
                }
            }
            if (mirror == null) {
                continue;
            }

            SortedMap<String, String> explicit = render(
                    mirror.getElementValues(), printer);
            SortedMap<String, String> effective = render(
                    elements.getElementValuesWithDefaults(mirror), printer);
            String name = ((TypeElement) element).getQualifiedName().toString();

            try {
                FileObject output = processingEnv.getFiler().createResource(
                        StandardLocation.CLASS_OUTPUT, "",
                        "META-INF/demo/policies/" + name + ".txt", element);
                try (Writer writer = output.openWriter()) {
                    writer.write("type=" + name + "\n");
                    writer.write("explicitKeys="
                            + String.join(",", explicit.keySet()) + "\n");
                    for (Map.Entry<String, String> entry : effective.entrySet()) {
                        writer.write(entry.getKey() + "=" + entry.getValue() + "\n");
                    }
                }
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot write policy for " + name + ": "
                                + exception.getMessage(), element);
            }
        }
        return true;
    }

    private static SortedMap<String, String> render(
            Map<? extends ExecutableElement, ? extends AnnotationValue> values,
            Printer printer) {
        SortedMap<String, String> result = new TreeMap<>();
        values.forEach((method, value) -> result.put(
                method.getSimpleName().toString(), value.accept(printer, null)));
        return result;
    }

    private static final class Printer
            extends SimpleAnnotationValueVisitor9<String, Void> {
        private final Elements elements;

        Printer(Elements elements) {
            this.elements = elements;
        }

        @Override
        protected String defaultAction(Object value, Void unused) {
            return String.valueOf(value);
        }

        @Override
        public String visitString(String value, Void unused) {
            return "\"" + value.replace("\\", "\\\\")
                    .replace("\"", "\\\"") + "\"";
        }

        @Override
        public String visitType(TypeMirror value, Void unused) {
            return value.toString();
        }

        @Override
        public String visitEnumConstant(VariableElement value, Void unused) {
            return value.getSimpleName().toString();
        }

        @Override
        public String visitArray(List<? extends AnnotationValue> values,
                                 Void unused) {
            StringJoiner joiner = new StringJoiner(", ", "[", "]");
            for (AnnotationValue value : values) {
                joiner.add(value.accept(this, null));
            }
            return joiner.toString();
        }

        @Override
        public String visitAnnotation(AnnotationMirror value, Void unused) {
            StringJoiner joiner = new StringJoiner(", ", "(", ")");
            render(elements.getElementValuesWithDefaults(value), this)
                    .forEach((name, rendered) ->
                            joiner.add(name + "=" + rendered));
            return "@" + value.getAnnotationType() + joiner;
        }
    }
}
~~~

**Cách code hoạt động:**

1. **round.getElementsAnnotatedWith(Policy.class)** lấy các khai báo có annotation, trong ví dụ là **demo.app.Job**.
2. **element.getAnnotationMirrors()** và **candidate.getAnnotationType().asElement()** xác định đúng annotation mang qualified name **demo.model.Policy**.
3. **mirror.getElementValues()** cung cấp map chỉ gồm các giá trị ghi tường minh; **elements.getElementValuesWithDefaults(mirror)** trả toàn bộ element values, bao gồm defaults.
4. Hàm **render(...)** chuyển mỗi **ExecutableElement.getSimpleName()** thành key và dùng **value.accept(printer, null)** để chuyển value thành text theo từng loại.
5. **TreeMap** sắp xếp các element names cho output có thứ tự ổn định, không phụ thuộc thứ tự iteration của map gốc.
6. **Printer.visitType(...)** nhận class literal dưới dạng **TypeMirror**, không dùng class loading. **visitEnumConstant(...)** nhận **VariableElement**.
7. **visitAnnotation(...)** đọc annotation lồng nhau bằng **getElementValuesWithDefaults(...)**, còn **visitArray(...)** xử lý từng AnnotationValue thành viên.
8. **Filer.createResource(CLASS_OUTPUT, ...)** viết resource có tên ổn định cho từng annotated class; phần **name** là qualified name, nên hai class ở package khác nhau không phải cùng một path.
9. **round.processingOver()** chặn việc processor cố tạo output lần nữa ở final round.
10. Khi không ghi được resource, **Messager** báo Diagnostic.ERROR tại element, để build thất bại rõ ràng.

**Giới hạn ví dụ:** Processor dùng class **Policy.class** để gọi **getElementsAnnotatedWith(...)**, trong khi phần đọc giá trị thực sự được thực hiện bằng mirror/visitor. Cách này tiện khi annotation API của ứng dụng là dependency mà processor đã biết. Với processor tổng quát nhận annotation type chưa được tải trong processor classloader, có thể tìm **TypeElement** bằng qualified name qua **Elements.getTypeElement(...)** và thao tác hoàn toàn trên model.

### 7.4. Code ứng dụng: src/demo/app/Job.java

~~~java
package demo.app;

import demo.model.Policy;

@Policy(
        label = "billing",
        handler = java.util.ArrayList.class,
        level = Policy.Level.HIGH)
public final class Job {}
~~~

Source **chỉ truyền ba giá trị** label, handler và level. Hai element **meta** và **retries** không có trong phần khai báo annotation nên sẽ dùng default.

### 7.5. Đọc resource: src/demo/app/Main.java

~~~java
package demo.app;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    public static void main(String[] args) throws Exception {
        String path = "META-INF/demo/policies/demo.app.Job.txt";
        try (InputStream input =
                     Main.class.getClassLoader().getResourceAsStream(path)) {
            if (input == null) {
                throw new IllegalStateException("Missing resource " + path);
            }
            System.out.print(
                    new String(input.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
~~~

Main **không dùng annotation reflection**. Nó chỉ đọc metadata do processor viết khi biên dịch, do đó **RetentionPolicy.SOURCE** vẫn đủ cho use case.

### 7.6. Lệnh biên dịch và chạy trên Bash/Linux/macOS

Chạy trong thư mục **annotation-mirror-demo**:

~~~bash
mkdir -p build/processor build/app

javac -encoding UTF-8 --release 17 \
    -d build/processor \
    src/demo/model/Policy.java \
    src/demo/processor/PolicyProcessor.java

javac -encoding UTF-8 --release 17 \
    -cp build/processor \
    -processorpath build/processor \
    -processor demo.processor.PolicyProcessor \
    -d build/app \
    src/demo/app/Job.java \
    src/demo/app/Main.java

java -cp "build/app:build/processor" demo.app.Main
~~~

**Stdout chính xác:**

~~~text
type=demo.app.Job
explicitKeys=handler,label,level
handler=java.util.ArrayList
label="billing"
level=HIGH
meta=@demo.model.Policy.Meta(code="fallback")
retries=[1, 3]
~~~

**Điểm nổi bật:**

- **explicitKeys=handler,label,level** không chứa **meta,retries**, vì source không ghi các element đó.
- Bảng effective values có đủ **handler,label,level,meta,retries** nhờ **Elements.getElementValuesWithDefaults(...)**.
- **handler=java.util.ArrayList** được tạo từ **TypeMirror**, không phải **java.lang.Class**.
- **level=HIGH** được tạo từ **VariableElement** của enum constant.
- **meta=@demo.model.Policy.Meta(code="fallback")** được tạo bằng visitor đệ quy.
- **retries=[1, 3]** được tạo bằng visitor của array và từng int value.
- Các tên key được sắp xếp alphabet bằng TreeMap để stdout có thứ tự xác định.

### 7.7. Lệnh tương đương trên Windows PowerShell

Trên Windows, đường phân cách các mục trong classpath của **java** là dấu **;**:

~~~powershell
New-Item -ItemType Directory -Force build/processor,build/app | Out-Null

javac -encoding UTF-8 --release 17 -d build/processor src/demo/model/Policy.java src/demo/processor/PolicyProcessor.java

javac -encoding UTF-8 --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.PolicyProcessor -d build/app src/demo/app/Job.java src/demo/app/Main.java

java -cp "build/app;build/processor" demo.app.Main
~~~

Stdout cũng đúng bảy dòng như trên. Các lệnh **javac** thông thường không in thông báo thành công nếu không có cảnh báo/lỗi.

### 7.8. Output sau khi chạy

~~~text
build/
├── processor/
│   └── demo/
│       ├── model/
│       │   ├── Policy.class
│       │   ├── Policy$Level.class
│       │   └── Policy$Meta.class
│       └── processor/
│           ├── PolicyProcessor.class
│           └── PolicyProcessor$Printer.class
└── app/
    ├── demo/app/
    │   ├── Job.class
    │   └── Main.class
    └── META-INF/demo/policies/
        └── demo.app.Job.txt
~~~

**-processorpath** dùng để công cụ biên dịch nạp processor, còn **-cp** dùng để source ứng dụng phân giải annotation. **-d build/app** là class output root và vị trí **CLASS_OUTPUT** để Filer tạo resource.

Chương trình đã được kiểm chứng trên **OpenJDK 24.0.2**, biên dịch cả processor và source ứng dụng với **--release 17**; resource tồn tại và stdout khớp chính xác bảy dòng trên.

## 8. Quan sát annotation processing rounds

Có thể thêm **-XprintRounds** vào lệnh javac biên dịch ứng dụng:

~~~bash
javac -encoding UTF-8 --release 17 \
    -XprintRounds \
    -cp build/processor \
    -processorpath build/processor \
    -processor demo.processor.PolicyProcessor \
    -d build/app \
    src/demo/app/Job.java \
    src/demo/app/Main.java
~~~

Trên JDK đã kiểm thử, thông tin rounds:

~~~text
Round 1:
    input files: {demo.app.Job, demo.app.Main}
    annotations: [demo.model.Policy]
    last round: false
Round 2:
    input files: {}
    annotations: []
    last round: true
~~~

Processor không tạo **Java source mới**, chỉ tạo resource. Vì vậy ở ví dụ này có một round xử lý nguồn ban đầu rồi đến final round. **Số rounds không phải con số cố định:** khi processor khác sinh Java source, sẽ có thêm các rounds tùy tình huống. **-XprintRounds** là diagnostic của javac, không phải stdout chương trình.

## 9. Dùng AnnotationValue.getValue() đúng cách

Nếu không muốn dùng visitor, có thể kiểm tra loại object mà **getValue()** trả. Khi code đã biết annotation element có dạng cụ thể, làm như sau:

~~~java
// Mảnh minh họa với một AnnotationValue value nhận từ model.
Object raw = value.getValue();

if (raw instanceof TypeMirror type) {
    // Giá trị Class<?> được mô hình hóa bằng TypeMirror.
} else if (raw instanceof VariableElement enumConstant) {
    // Giá trị enum được mô hình hóa bằng VariableElement.
} else if (raw instanceof AnnotationMirror nested) {
    // Giá trị annotation lồng nhau.
} else if (raw instanceof List<?> items) {
    // Array: từng item cần được xử lý như AnnotationValue.
}
~~~

Đoạn code minh họa này không tự chạy độc lập và bỏ qua wrapper/chuỗi. Với array, nên dùng **List<? extends AnnotationValue>** sau khi kiểm tra kiểu dữ liệu model đã biết. Với code xử lý mọi loại giá trị, **AnnotationValueVisitor** thường gọn và tránh trường hợp ép kiểu nhầm.

### 9.1. Vì sao không dùng Class<?> cho class literal?

Giả sử annotation có **Class<?> handler()** và source dùng:

~~~java
@Policy(label = "billing", handler = java.util.ArrayList.class)
public final class Job {}
~~~

Trong mô hình compiler, **handler** được biểu diễn bằng **TypeMirror**. Một class mới đang được biên dịch có thể chưa được load thành Class object, nên Java model API cố ý tránh yêu cầu class loading.

Nếu dùng proxy annotation qua **element.getAnnotation(Policy.class)**, gọi một method có kiểu **Class** có thể ném **MirroredTypeException**, và method trả **Class[]** có thể ném **MirroredTypesException**. Đó là một cách tiếp cận có contract riêng, nhưng khi cần phân tích source có type chưa nạp được, **AnnotationMirror + TypeMirror** thường là cách rõ ràng và tổng quát hơn.

Không xử lý vấn đề bằng cách luôn gọi **Class.forName**: điều đó có thể nạp class sai môi trường, thất bại do class chưa tồn tại hoặc gây tác động không mong muốn.

### 9.2. Enum và nested annotation không phải object runtime tương ứng

- Một enum annotation value được mô hình hóa bằng **VariableElement** của constant, chứ không cần tạo enum instance để tra tên.
- Một nested annotation value được mô hình hóa bằng **AnnotationMirror** mới; đọc element của nó với cùng cơ chế.
- Array có thể chứa nested annotations hoặc enum constants, nên cần đi vào từng **AnnotationValue** một cách đệ quy.
- Nếu kiểu khai báo là **String**, giá trị trả về là String; nếu là primitive, giá trị là boxed primitive tương ứng.

## 10. Chọn getAnnotationMirrors, getAllAnnotationMirrors và getAnnotation

| API | Mục đích | Khi nào phù hợp |
| --- | --- | --- |
| **Element.getAnnotationMirrors()** | Đọc danh sách annotation trực tiếp trên declaration element | Processor quan tâm source annotation khai báo tại chỗ |
| **Elements.getAllAnnotationMirrors(element)** | Có thể xét cả annotation hiện diện qua kế thừa | Quy tắc của compiler cần xem effective annotations trên class hierarchy |
| **Element.getAnnotation(Policy.class)** | Proxy annotation typed theo Class của annotation | Processor có annotation API trên classpath, biết contract và chấp nhận quy tắc về class-typed elements |
| **AnnotationMirror.getElementValues()** | Tách riêng các value được ghi rõ | Kiểm tra ý định người viết/source |
| **Elements.getElementValuesWithDefaults(...)** | Lấy toàn bộ effective annotation values | Code generation và kiểm tra cấu hình sau khi áp dụng defaults |

Một ví dụ cho thấy ranh giới: nếu processor kiểm tra **@Inherited** trên superclass, **getAnnotationMirrors()** của subclass không tự tương đương với việc tra cứu annotation có hiệu lực theo kế thừa. Hãy lựa chọn API theo quy tắc Java mà ứng dụng định nghĩa.

## 11. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **getElementValues()** thiếu một key | Element đó dùng default, không được ghi tường minh | Dùng **getElementValuesWithDefaults** khi cần giá trị hiệu lực |
| **ClassCastException** khi cast value của Class<?> thành Class | Model trả **TypeMirror** | Dùng **visitType(...)** hoặc **TypeMirror** |
| **ClassCastException** khi cast enum thành enum instance | Model trả **VariableElement** | Dùng **visitEnumConstant(...)** |
| **ClassCastException** khi cast annotation lồng nhau | Model trả **AnnotationMirror** | Dùng **visitAnnotation(...)**, xử lý đệ quy |
| Array bị coi thành một value đơn | Model trả List của AnnotationValue | Dùng **visitArray(...)**, duyệt phần tử |
| Không tìm được annotation | Tìm sai qualified name, annotation ở vị trí khác, annotation kế thừa hoặc repeated annotation container | Kiểm tra **getAnnotationMirrors**, **getAllAnnotationMirrors**, target và model |
| Output thiếu defaults | Chỉ dùng **getElementValues()** | Thêm **Elements.getElementValuesWithDefaults(...)** |
| Output không ổn định giữa builds | Ghi Map không sắp xếp, format phụ thuộc môi trường | Sort key và chuẩn hóa encoding/serialization |
| **MirroredTypeException** từ getAnnotation(...) | Đọc method Class-valued qua proxy annotation | Dùng **AnnotationMirror/TypeMirror** thay vì yêu cầu Class runtime |
| Processor không chạy | Thiếu cấu hình annotation processing hoặc processor path | Khai báo **-processor** và đường dẫn processor chính xác |
| Resource không có ở runtime | CLASS_OUTPUT sai, chưa đóng Writer, đóng gói mất resource hoặc runtime classpath không chứa file | Kiểm tra **-d**, artifact cuối và **getResourceAsStream** |
| Output trùng khi nhiều class được annotate | Processor dùng cùng resource name | Dùng qualified name trong resource path và quản lý ownership |
| Bản code mới compile trên máy local nhưng lỗi CI | Processor version, JDK, source release hoặc classpath khác nhau | Kiểm tra thực tế compiler options và processor dependencies |

### 11.1. Diagnostic tốt cần có ngữ cảnh

Trong processor, nếu phát hiện annotation element có value không hợp lệ, hãy báo bằng **Messager.printMessage(Diagnostic.Kind.ERROR, ..., element, annotationMirror, annotationValue)** ở overload phù hợp khi muốn gắn lỗi tới annotation/value, thay vì in một dòng không có vị trí source.

Đây là **mảnh minh họa**:

~~~java
// Các biến messenger, element, mirror và value do processor cung cấp.
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Giá trị annotation không được chấp nhận",
        element, mirror, value);
~~~

Một số environment có thể báo diagnostic ở mức location khác nhau, nhưng Element/AnnotationMirror/AnnotationValue là ngữ cảnh phù hợp theo contract API.

Trong chương trình ví dụ, IOException từ Filer được báo tại element để build thất bại rõ ràng. **FilerException** là một dạng IOException khi output path/type bị trùng trong một processing run; không nên “sửa” bằng cách ghi đè ngẫu nhiên.

### 11.2. Vì sao các tệp cũ có thể gây hiểu nhầm?

Nếu bạn tắt processor mà vẫn thấy resource hoặc generated class từ build trước, có thể đang chạy trên một output directory chưa được dọn. Hãy kiểm thử trong **build root sạch** hoặc bằng hệ thống build quản lý output/incremental compilation đúng hợp đồng. Đừng kết luận annotation processing đã chạy chỉ vì file từng tồn tại.

Mỗi lần build, xác nhận javac exit code (hoặc **JavaCompiler.CompilationTask.call()**) và compiler diagnostics; đừng chỉ nhìn sự tồn tại của file.

## 12. Nâng cấp ví dụ và kiểm thử

### 12.1. Thử thay giá trị default

Bổ sung giá trị retries tường minh:

~~~java
@Policy(
        label = "billing",
        handler = java.util.ArrayList.class,
        level = Policy.Level.HIGH,
        retries = {2, 5})
public final class Job {}
~~~

Khi biên dịch lại trên output directory sạch, dòng **explicitKeys** sẽ có thêm **retries** và dòng effective **retries=[2, 5]**. Nếu không ghi **retries**, nó chỉ xuất hiện trong effective values vì dùng default **{1,3}**.

### 12.2. Thử nested annotation

Sửa Job:

~~~java
@Policy(
        label = "billing",
        handler = java.util.ArrayList.class,
        level = Policy.Level.HIGH,
        meta = @Policy.Meta(code = "signed"))
public final class Job {}
~~~

Khi đó **meta** trở thành key tường minh. Visitor sẽ xử lý nested AnnotationMirror và ghi **meta=@demo.model.Policy.Meta(code="signed")**; **retries** vẫn dùng default.

### 12.3. Thử Class-valued element

Đổi handler sang một type hợp lệ khác có trên compilation path, ví dụ:

~~~java
@Policy(label = "billing", handler = java.util.HashMap.class)
public final class Job {}
~~~

Giá trị handler trong resource sẽ thành **java.util.HashMap**; visitor vẫn nhận TypeMirror, không tải class qua reflection.

### 12.4. Tự viết compile test

Một bộ kiểm thử nên xác minh:

- **Job.java** có ba key tường minh, dù Effective Map có năm element.
- Default arrays và nested annotation được render đúng.
- Sắp xếp key tạo output ổn định giữa hai clean builds cùng toolchain.
- Mỗi annotated type tạo resource path duy nhất.
- Khi một element bắt buộc **label()** bị bỏ trống, compiler báo lỗi vì thiếu annotation element chưa có default.
- Khi annotation không đúng target, compiler báo lỗi khai báo.
- Khi processor path bị thiếu, javac báo lỗi hoặc không thể tạo resource theo cách cấu hình cụ thể.
- Generated resource có mặt trong output directory và trong artifact cuối nếu build đóng gói.
- Nếu processor báo ERROR, build fail; không phát hành output đã tạo một phần.

## 13. Những lưu ý thiết kế khi dùng thực tế

1. **Giữ dependency processor tường minh.** Trên JDK mới, không nên giả định việc processor JAR tình cờ có trên classpath sẽ luôn kích hoạt processing. Dùng **-processor**, processor path và cấu hình build tool có chủ đích.
2. **Processor là code chạy trong môi trường build.** Không chạy processor không tin cậy với quyền truy cập secret/network rộng; annotation model không tự tạo sandbox.
3. **Định danh theo qualified name.** Không so sánh annotation theo simple name khi có thể trùng package; không dùng object identity của mirror.
4. **Dùng API model thay reflection** khi type đang biên dịch chưa thể nạp. Với class literals, xử lý TypeMirror và dùng Types/Elements để so sánh khi cần.
5. **Quản lý defaults có ý thức.** Phân biệt source intent (explicit) với effective configuration; serializer phải chọn đúng nhu cầu.
6. **Kết quả phải tái lập.** Với metadata được ghi ra file, sắp xếp các key và danh sách, tránh timestamp/random và thực hiện encoding/escaping phù hợp.
7. **Không lưu đối tượng model vượt lifecycle processing** rồi mong dùng ở runtime hoặc một compilation không liên quan. Cần chuyển thành dữ liệu độc lập nếu muốn cache.
8. **Tránh tạo resource trùng tên.** Filer quản lý output theo đường dẫn trong processing run; nhiều class/processor cùng ghi một resource phải có chiến lược aggregate hoặc owner rõ.
9. **Kiểm thử API và artifact cuối.** Thử cả giá trị mặc định, array, enum, nested annotation, Class-valued elements, repeated/inherited annotations nếu contract của dự án yêu cầu.

## Ghi nhớ

- **AnnotationMirror** cho biết annotation nào hiện diện và những element nào được ghi tường minh.
- **AnnotationValue** chứa biểu diễn giá trị theo **mô hình ngôn ngữ**, không phải luôn là object runtime của type được annotate.
- **Elements.getElementValuesWithDefaults** là cách chuẩn lấy effective values.
- **Class<?> → TypeMirror**, **enum → VariableElement**, **nested annotation → AnnotationMirror**, **array → List<AnnotationValue>**.
- **AnnotationValueVisitor** giúp xử lý từng loại có kiểm soát.
- Đừng nhầm khai báo trực tiếp với kế thừa, compile-time model với runtime reflection, hay trạng thái build với sự hiện diện của file cũ.

**Tài liệu JDK chính thức (API vẫn được hỗ trợ):**

- [AnnotationMirror — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html)
- [AnnotationValue — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html)
- [AnnotationValueVisitor — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/AnnotationValueVisitor.html)
- [SimpleAnnotationValueVisitor9 — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/SimpleAnnotationValueVisitor9.html)
- [Elements.getElementValuesWithDefaults — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Elements.html)
- [Element.getAnnotationMirrors — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html)
- [javac — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)