# Đọc phần tử khai báo tường minh và giá trị mặc định trong Java Annotation Processing

Khi Java annotation có phần tử (*element*) khai báo **default**, một lần sử dụng annotation có thể **chỉ truyền một số phần tử** và để những phần còn lại lấy giá trị mặc định. Nếu viết công cụ xử lý annotation trong lúc biên dịch, cần phân biệt hai câu hỏi:

1. **Người viết mã đã chỉ định tường minh những phần tử nào tại nơi gắn annotation?**
2. **Giá trị hiệu lực của tất cả phần tử là gì sau khi áp dụng những giá trị mặc định từ kiểu annotation?**

Trong mô hình ngôn ngữ Java (**javax.lang.model**) và Annotation Processing API (**javax.annotation.processing**), hai API trung tâm cho hai câu hỏi này là:

- **AnnotationMirror.getElementValues()**: trả về **chỉ các cặp phần tử–giá trị được khai báo tường minh** trong annotation đang xét.
- **Elements.getElementValuesWithDefaults(AnnotationMirror)**: trả về các cặp phần tử–giá trị, **bao gồm cả những phần tử nhận default** khi không được chỉ định tường minh.

Chúng thường được dùng cùng với **ExecutableElement.getDefaultValue()**, cho phép truy vấn **giá trị default trong khai báo một phần tử của annotation type**. Ba API có vai trò khác nhau và không nên đánh đồng.

## 1. Một ví dụ cụ thể: annotation được dùng thiếu bớt phần tử

Khai báo kiểu annotation:

~~~java
@interface Endpoint {
    String path();
    int retries() default 3;
    boolean enabled() default true;
}
~~~

Gắn annotation lên class:

~~~java
@Endpoint(path = "/orders", enabled = false)
class OrderApi {
}
~~~

Ở đây:

- **path()** không có default nên là phần tử **bắt buộc**. Nơi sử dụng phải cung cấp **path = "/orders"**.
- **retries()** có **default 3**. Nơi sử dụng không cung cấp retries, nên khi lấy giá trị hiệu lực, nó là **3**.
- **enabled()** có **default true**, nhưng nơi sử dụng **chỉ định tường minh enabled = false**. Vì vậy giá trị hiệu lực là **false**, không bị default ghi đè.

Kết quả mong đợi khi hỏi về **phần tử tường minh**:

~~~text
enabled=false
path=/orders
~~~

Khi hỏi về **giá trị hiệu lực, gồm default**:

~~~text
enabled=false
path=/orders
retries=3
~~~

Thứ tự dòng ở đây được sắp xếp theo tên để dễ đọc; API không yêu cầu bạn xử lý map theo thứ tự bảng trên. Phần ví dụ Java 17+ ở dưới sẽ tự sắp xếp để cho đầu ra ổn định.

### Hai lớp dữ liệu cần ghi nhớ

**Giá trị đã viết trong mã sử dụng annotation** và **giá trị lấy từ khai báo annotation type** không phải cùng một nguồn.

| Element | Khai báo trên Endpoint | Viết tường minh tại @Endpoint trên OrderApi? | Giá trị hiệu lực |
| --- | --- | --- | --- |
| **path()** | Không có default | Có: **"/orders"** | "/orders" |
| **retries()** | **default 3** | Không | 3 |
| **enabled()** | **default true** | Có: **false** | false |

Nếu processor chỉ muốn báo những tùy chọn mà tác giả đã **chủ động ghi ở vị trí sử dụng**, phải xem bản đồ tường minh. Nếu processor cần tạo cấu hình đầy đủ để sinh mã hoặc kiểm tra ngưỡng, nên xem bản đồ **bao gồm default**.

## 2. AnnotationMirror đại diện cho gì?

Trong JSR 269, **AnnotationMirror** thuộc package **javax.lang.model.element**. Nó là **mô hình của một annotation** mà trình biên dịch nhìn thấy khi xử lý source và symbols.

Ví dụ một processor nhận **TypeElement** đại diện class OrderApi, rồi đọc:

~~~java
for (AnnotationMirror mirror : typeElement.getAnnotationMirrors()) {
    System.out.println(mirror.getAnnotationType());
}
~~~

Đây là một đoạn minh họa bên trong processor; **typeElement** đã được lấy từ compiler model, không phải một biến tồn tại tự động trong chương trình Java thông thường.

Những thành phần liên quan:

- **Element**: khai báo chương trình như package, class, interface, method, field hoặc parameter.
- **TypeElement**: một loại Element biểu diễn khai báo kiểu, chẳng hạn class OrderApi.
- **AnnotationMirror**: một annotation gắn lên khai báo đang xử lý.
- **ExecutableElement**: đại diện cho một phần tử của annotation type, ví dụ phương thức **retries()**.
- **AnnotationValue**: giá trị một element, ví dụ **3**, **false** hoặc chuỗi **"/orders"**.
- **ProcessingEnvironment**: bộ tiện ích dành cho processor, trong đó có **getElementUtils()** trả về **Elements**.
- **Elements**: tiện ích mô hình ngôn ngữ, có phương thức **getElementValuesWithDefaults(...)**.

**AnnotationMirror không phải một đối tượng Annotation reflection runtime.** Dù cả hai liên quan đến metadata, AnnotationMirror thuộc mô hình của compiler; kiểu như **java.lang.Class** và **java.lang.reflect.Method** thuộc mô hình reflection runtime.

Trong chương trình processor, nên so sánh kiểu annotation qua mô hình Java, ví dụ **mirror.getAnnotationType()** hoặc **TypeElement**, thay vì cố nạp class nguồn bằng Class.forName.

## 3. Chỉ đọc những phần tử được chỉ định tường minh

API:

~~~java
Map<? extends ExecutableElement, ? extends AnnotationValue>
        values = mirror.getElementValues();
~~~

Map này chỉ chứa **những phần tử có giá trị được viết tường minh** tại lần gắn annotation được mô tả bởi mirror.

Ví dụ:

~~~java
@Endpoint(path = "/orders", enabled = false)
class OrderApi {}
~~~

Map chứa các khóa tương ứng với **path()** và **enabled()**. Nó **không chứa retries()**, dù retries có default 3 và giá trị hiệu lực của retries là 3.

Lặp qua map:

~~~java
for (Map.Entry<? extends ExecutableElement,
               ? extends AnnotationValue> entry
        : mirror.getElementValues().entrySet()) {

    String elementName =
            entry.getKey().getSimpleName().toString();

    AnnotationValue value = entry.getValue();

    System.out.println(elementName + "=" + value);
}
~~~

Đây là code minh họa bên trong processor với import **java.util.Map**, **javax.lang.model.element.ExecutableElement**, **AnnotationValue**. Nó in các giá trị dưới dạng biểu diễn của AnnotationValue; chẳng hạn giá trị chuỗi có thể được biểu diễn với dấu ngoặc kép. Nếu cần chuyển sang các object mô hình cụ thể, phải xem **AnnotationValue.getValue()**.

**Cảnh báo quan trọng:** nếu người viết chỉ định một giá trị **đúng bằng default**, nó **vẫn được coi là tường minh**.

~~~java
@Endpoint(path = "/orders", retries = 3)
class ExplicitDefaultApi {}
~~~

Đối với trường hợp này, **retries()** sẽ xuất hiện trong **getElementValues()**, dù số 3 bằng default 3. API trả lời câu hỏi **“được viết ra không?”**, không phải **“khác default không?”**.

### Marker annotation và bản đồ rỗng

Một marker annotation không khai báo phần tử:

~~~java
@interface Ready {}

@Ready
class Service {}
~~~

**AnnotationMirror.getElementValues()** cho Ready là **map rỗng**. Điều này đúng vì annotation không có phần tử nào, chứ **không có nghĩa annotation vắng mặt**. Trước hết processor phải tìm được **AnnotationMirror** tương ứng với Ready; sau đó mới xem map phần tử bên trong.

Một annotation có tất cả phần tử đều có default và được dùng dưới dạng **@SomeAnnotation** cũng có thể cho **map tường minh rỗng**, nhưng **getElementValuesWithDefaults(...)** sẽ trả các element mặc định.

## 4. Lấy đầy đủ giá trị, kể cả default

Khi cần cấu hình hiệu lực, dùng tiện ích **Elements**:

~~~java
Map<? extends ExecutableElement, ? extends AnnotationValue>
        effective = processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
~~~

**processingEnv** là trường được AbstractProcessor cung cấp sau khi processor khởi tạo. Kết quả là map có những cặp element–value được chỉ định tường minh và những cặp còn lại lấy từ default khai báo trong annotation type.

Với ví dụ OrderApi:

~~~text
path=/orders      (tường minh)
enabled=false     (tường minh)
retries=3         (mặc định)
~~~

Trong một processor, đây là cách thuận tiện để sinh cấu hình đã được áp dụng default, tránh phải tự duyệt mọi element rồi tra default cho từng tên.

Đừng dùng một phép thử như **containsKey("retries")** trực tiếp vì map này có **khóa là ExecutableElement**, không phải String. Nếu cần truy vấn theo tên, hãy duyệt khóa và dùng **getSimpleName()**, hoặc chuyển qua một cấu trúc được thiết kế riêng.

### So sánh đúng hai bản đồ

| Câu hỏi | API nên dùng |
| --- | --- |
| Tác giả viết cụ thể những cặp element=value nào? | **mirror.getElementValues()** |
| Giá trị hiệu lực của toàn bộ annotation là gì? | **elements.getElementValuesWithDefaults(mirror)** |
| Kiểu annotation này khai báo default nào cho element retries? | **ExecutableElement.getDefaultValue()** |
| Annotation được gắn lên phần tử chương trình nào? | **Element.getAnnotationMirrors()** hoặc tìm bằng RoundEnvironment |
| Cần đọc annotation khi ứng dụng đang chạy? | **reflection getAnnotation(...)** và RUNTIME retention |

**Không sửa map mà API trả về** để “gắn” default hoặc giả định map có thể mutate tùy ý. Trong công cụ thực tế, có thể sao chép sang **TreeMap<String, ...>** hoặc immutable data structure của riêng chương trình.

## 5. Đọc default ngay trên khai báo phần tử

Khi có **ExecutableElement** đại diện một phương thức của annotation type:

~~~java
AnnotationValue declaredDefault =
        annotationElement.getDefaultValue();
~~~

- Nếu annotation element có **default**, trả về **AnnotationValue** biểu diễn giá trị mặc định đó.
- Nếu element **không có default**, trả về **null**.
- Đây là thông tin của **khai báo element trong annotation type**, không phải của một lần sử dụng annotation cụ thể.

Ví dụ với Endpoint:

~~~java
interface-like Endpoint {
    // Sơ đồ, KHÔNG phải cú pháp Java:
    path()       : no default
    retries()    : default 3
    enabled()    : default true
}
~~~

Sơ đồ phía trên chỉ diễn giải vai trò của API, không phải tệp mã nguồn có thể biên dịch; cú pháp Java thực là **@interface Endpoint** ở phần 1.

Đoạn processor để xem default:

~~~java
TypeElement annotationType =
        (TypeElement) mirror.getAnnotationType().asElement();

for (Element member : annotationType.getEnclosedElements()) {
    if (member instanceof ExecutableElement element) {
        AnnotationValue defaultValue = element.getDefaultValue();

        System.out.println(element.getSimpleName() + " -> "
                + (defaultValue == null
                        ? "<required>" : defaultValue));
    }
}
~~~

Ở đây **mirror.getAnnotationType()** trả về **DeclaredType** và **asElement()** trả về khai báo type tương ứng, sau đó lấy các **ExecutableElement** bên trong.

**getDefaultValue()** có thể trả **null** để báo không có default; còn **getElementValuesWithDefaults(...)** không tự tạo giá trị cho phần tử bắt buộc bị bỏ trống trong một annotation không hợp lệ. Khi source thiếu một phần tử bắt buộc, compiler sẽ báo lỗi; công cụ không nên trông chờ một giá trị “null hợp lệ” xuất hiện để thay thế.

### Default và giá trị có cùng số

Giả sử khai báo **default 3**. Hai source sau có cùng giá trị hiệu lực:

~~~java
@Endpoint(path = "/a")
class A {}

@Endpoint(path = "/b", retries = 3)
class B {}
~~~

Nhưng đối với **retries**:

- **A** không có retries trong map tường minh.
- **B** có retries trong map tường minh.
- Cả A và B có retries = 3 trong map đầy đủ với default.

Nếu yêu cầu là **khôi phục quyết định cấu hình của tác giả**, khác biệt này quan trọng. Nếu yêu cầu chỉ là **thi hành cấu hình**, giá trị hiệu lực thường đủ.

## 6. Ví dụ hoàn chỉnh Java 17+: đọc explicit và default bằng processor

Thí nghiệm dưới đây tạo một **annotation processor** đọc annotation có retention SOURCE, sinh **một class báo cáo** để chương trình main in kết quả. Nó giúp quan sát chính xác sự khác biệt hai map mà không cần dựa vào thứ tự duyệt nội bộ hoặc định dạng diagnostic của javac.

### Cấu trúc dự án

Tạo bốn tệp:

~~~text
project/
├── processor/
│   └── demo/
│       └── EndpointProcessor.java
└── src/
    └── demo/
        ├── Endpoint.java
        ├── OrderApi.java
        └── Main.java
~~~

Thư mục **processor** chứa mã processor; thư mục **src** chứa kiểu annotation và chương trình ứng dụng. Processor không tham chiếu trực tiếp class Endpoint tại lúc build processor, nên có thể biên dịch riêng.

### Tệp 1 — src/demo/Endpoint.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Endpoint {
    String path();
    int retries() default 3;
    boolean enabled() default true;
}
~~~

**SOURCE retention** được chọn có chủ ý: processor trong javac vẫn phân tích được annotation, nhưng bản annotation này sẽ không được giữ lại cho runtime reflection.

### Tệp 2 — src/demo/OrderApi.java

~~~java
package demo;

@Endpoint(path = "/orders", enabled = false)
public class OrderApi {
}
~~~

Chỉ **path** và **enabled** được ghi tường minh; **retries** dùng default 3.

### Tệp 3 — processor/demo/EndpointProcessor.java

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Map;
import java.util.Set;
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
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Endpoint")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class EndpointProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotationTypes,
            RoundEnvironment round) {

        if (round.processingOver() || generated) {
            return true;
        }

        for (TypeElement annotationType : annotationTypes) {
            for (Element annotated :
                    round.getElementsAnnotatedWith(annotationType)) {

                for (AnnotationMirror mirror :
                        annotated.getAnnotationMirrors()) {

                    if (!mirror.getAnnotationType().toString()
                            .equals("demo.Endpoint")) {
                        continue;
                    }

                    String explicit = describe(
                            mirror.getElementValues());

                    String effective = describe(
                            processingEnv.getElementUtils()
                                    .getElementValuesWithDefaults(mirror));

                    try {
                        JavaFileObject file = processingEnv.getFiler()
                                .createSourceFile(
                                        "demo.generated.AnnotationReport",
                                        annotated);

                        try (Writer writer = file.openWriter()) {
                            writer.write("package demo.generated;\n");
                            writer.write(
                                    "public final class AnnotationReport {\n");
                            writer.write(
                                    "  private AnnotationReport() {}\n");
                            writer.write(
                                    "  public static final String EXPLICIT = "
                                    + javaLiteral(explicit) + ";\n");
                            writer.write(
                                    "  public static final String EFFECTIVE = "
                                    + javaLiteral(effective) + ";\n");
                            writer.write("}\n");
                        }

                        generated = true;
                    } catch (IOException ex) {
                        processingEnv.getMessager().printMessage(
                                Diagnostic.Kind.ERROR,
                                "Unable to generate report: "
                                        + ex.getMessage(),
                                annotated);
                    }

                    return true;
                }
            }
        }

        return true;
    }

    private static String describe(
            Map<? extends ExecutableElement,
                ? extends AnnotationValue> values) {

        Map<String, String> sorted = new TreeMap<>();

        for (Map.Entry<? extends ExecutableElement,
                       ? extends AnnotationValue> entry
                : values.entrySet()) {

            String name = entry.getKey()
                    .getSimpleName().toString();

            Object rawValue = entry.getValue().getValue();
            sorted.put(name, String.valueOf(rawValue));
        }

        return sorted.toString();
    }

    private static String javaLiteral(String text) {
        return "\"" + text
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n") + "\"";
    }
}
~~~

**Giải thích các bước của processor:**

1. Processor được khai báo hỗ trợ annotation **demo.Endpoint** với **@SupportedAnnotationTypes**.
2. **RoundEnvironment.getElementsAnnotatedWith(annotationType)** lấy các khai báo được gắn Endpoint trong vòng xử lý. Đoạn code chỉ có một đối tượng là OrderApi.
3. **annotated.getAnnotationMirrors()** lấy những AnnotationMirror hiện diện trên khai báo. Processor chọn mirror có type **demo.Endpoint**.
4. **mirror.getElementValues()** chứa các giá trị tường minh: **enabled=false** và **path=/orders**.
5. **processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)** chứa thêm **retries=3**.
6. **describe(...)** dùng **TreeMap** sắp xếp khóa theo tên, nên đầu ra không phụ thuộc thứ tự map do compiler trả về.
7. **AnnotationValue.getValue()** trong ví dụ chỉ trả các kiểu đơn giản (**String**, **Boolean**, **Integer**), nên **String.valueOf(...)** đủ để biểu diễn theo ý muốn. Trong processor tổng quát, với class literal, enum, nested annotation hoặc array, cần xử lý các dạng Java language model riêng, không được giả định getValue() luôn là primitive/String.
8. **Filer.createSourceFile(...)** tạo source **demo.generated.AnnotationReport**, chứa hai string constant EXPLICIT và EFFECTIVE để Main in ra. **javaLiteral(...)** escape những ký tự cần thiết cho literal chuỗi Java ở các giá trị minh họa.
9. Trường **generated** và điều kiện **processingOver()** giúp tránh tạo lặp cùng một source ở nhiều processing round.
10. **return true** tuyên bố processor đã xử lý (*claim*) annotation types mà nó hỗ trợ. Không có nghĩa processor tự chạy ứng dụng Main.

Ví dụ cố ý giả định **chỉ một class được gắn Endpoint** trong lượt biên dịch. Trong dự án thực tế, hãy xử lý nhiều annotated elements và sinh tên tệp duy nhất cho từng class, hoặc tạo báo cáo tổng hợp sau khi đã xét toàn bộ input. Cần thiết kế quản lý vòng xử lý và lỗi duplicate file tương ứng.

### Tệp 4 — src/demo/Main.java

~~~java
package demo;

import demo.generated.AnnotationReport;

public class Main {
    public static void main(String[] args) {
        System.out.println("explicit="
                + AnnotationReport.EXPLICIT);
        System.out.println("effective="
                + AnnotationReport.EFFECTIVE);

        boolean visibleAtRuntime =
                OrderApi.class.getAnnotation(Endpoint.class) != null;

        System.out.println("runtimePresent="
                + visibleAtRuntime);
    }
}
~~~

**Main** sử dụng class được processor sinh. Dòng **getAnnotation(Endpoint.class)** sẽ trả null do Endpoint có SOURCE retention; đây là phép kiểm tra phụ để thấy compiler-model và reflection runtime là hai cơ chế khác nhau.

### Biên dịch và chạy

Từ thư mục **project**:

~~~bash
mkdir -p processor-out generated-src out
~~~

Trên Windows PowerShell, có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force processor-out,generated-src,out | Out-Null
~~~

**Pha 1: biên dịch processor.**

~~~bash
javac --release 17 -proc:none -d processor-out processor/demo/EndpointProcessor.java
~~~

**Pha 2: biên dịch source và gọi processor một cách tường minh.**

~~~bash
javac --release 17 -processorpath processor-out -processor demo.EndpointProcessor -s generated-src -d out src/demo/Endpoint.java src/demo/OrderApi.java src/demo/Main.java
~~~

**Pha 3: chạy ứng dụng.**

~~~bash
java -cp out demo.Main
~~~

**Stdout của lệnh java:**

~~~text
explicit={enabled=false, path=/orders}
effective={enabled=false, path=/orders, retries=3}
runtimePresent=false
~~~

Java compiler sinh thêm source:

~~~text
generated-src/demo/generated/AnnotationReport.java
~~~

Với nội dung về ý nghĩa tương đương:

~~~java
package demo.generated;
public final class AnnotationReport {
  private AnnotationReport() {}
  public static final String EXPLICIT =
      "{enabled=false, path=/orders}";
  public static final String EFFECTIVE =
      "{enabled=false, path=/orders, retries=3}";
}
~~~

**Lưu ý:** Các lệnh biên dịch có thể in diagnostic nếu công cụ hoặc môi trường có cấu hình đặc biệt. Bảng stdout ở trên mô tả **lệnh java chạy Main**, không tính thông báo javac. Thư mục generated-src chứa source do processor sinh; class file được javac đặt trong **out**.

### Thí nghiệm thay đổi cách viết annotation

Đổi **OrderApi.java** từ:

~~~java
@Endpoint(path = "/orders", enabled = false)
~~~

thành:

~~~java
@Endpoint(path = "/orders", enabled = false, retries = 3)
~~~

Vì **retries = 3** giờ đã được ghi tường minh, bản báo cáo **EXPLICIT** có thêm **retries=3**, trong khi **EFFECTIVE** vẫn như cũ. Nếu chạy lại thí nghiệm, nên dọn những tệp generated cũ hoặc tạo thư mục đầu ra mới, tránh lỗi **FilerException** hoặc nhầm binary cũ.

## 7. Vì sao không dùng trực tiếp Element.getAnnotation để phân biệt explicit/default?

Bên cạnh AnnotationMirror, compiler model cung cấp các tiện ích dạng annotation proxy:

~~~java
Endpoint endpoint =
        annotated.getAnnotation(Endpoint.class);

if (endpoint != null) {
    int retries = endpoint.retries();
}
~~~

Trong một processor đã biên dịch và có thể tham chiếu kiểu Endpoint, **Element.getAnnotation(Endpoint.class)** có thể trả đối tượng cung cấp giá trị hiệu lực của annotation, tương tự cách gọi element methods trên annotation object.

Tuy nhiên, nó **không phải API ưu tiên để lấy danh sách những phần tử đã viết tường minh**. Nếu **retries()** trả về 3, bạn không thể kết luận tác giả đã gõ **retries=3** hay không: 3 có thể đến từ default.

Vì vậy:

- **Muốn biết element nào được chỉ định tường minh:** dùng **AnnotationMirror.getElementValues()**.
- **Muốn bản đồ đầy đủ gồm default:** dùng **Elements.getElementValuesWithDefaults(...)**.
- **Muốn gọi element methods thuận tiện với annotation type đã biết:** có thể dùng **Element.getAnnotation(...)** khi thích hợp, nhưng cần hiểu giới hạn loại dữ liệu và khả năng đọc từng element.

**Một vấn đề quan trọng với class-valued annotation elements:** trên các proxy do compiler model cung cấp, lời gọi element trả về **Class** hoặc **Class[]** có thể ném **MirroredTypeException** hoặc **MirroredTypesException**, vì class nguồn chưa được nạp. Khi cần phân tích giá trị class literal tại compile time, dùng **AnnotationMirror/AnnotationValue** và **TypeMirror** thường bền vững hơn.

Không cố sửa lỗi đó bằng cách nạp class chưa tồn tại bằng **Class.forName(...)** trong processor. Annotation processing được thiết kế để làm việc với symbol và kiểu trong compiler model.

## 8. AnnotationValue.getValue() trả về những dạng nào?

**AnnotationValue** không đơn thuần là object runtime của từng element. Nó là một giá trị trong mô hình ngôn ngữ; tùy loại element, **getValue()** trả ra những kiểu mô hình thích hợp.

| Kiểu phần tử của annotation | Dạng giá trị trong AnnotationValue.getValue() |
| --- | --- |
| Primitive như **int**, **boolean**, **long** | Giá trị được đóng hộp, ví dụ Integer, Boolean, Long |
| **String** | String |
| **Class<?>** hoặc class literal | **TypeMirror**, không phải nhất thiết là java.lang.Class |
| Enum | **VariableElement** cho hằng enum |
| Annotation lồng nhau | **AnnotationMirror** |
| Mảng một chiều các kiểu hợp lệ | **List<? extends AnnotationValue>** |

Trong ví dụ processor, các kiểu đơn giản được chuyển sang String bằng **String.valueOf(...)**. Không sử dụng phương pháp đó làm lời giải chung cho mọi cấu trúc lồng nhau.

Khi viết processor tổng quát, Java cung cấp **AnnotationValueVisitor** và các lớp tiện ích như **SimpleAnnotationValueVisitor9**. Visitor cho phép phân nhánh rõ theo kiểu giá trị:

~~~java
AnnotationValue value = /* giá trị đã lấy từ map */;

value.accept(new javax.lang.model.util.SimpleAnnotationValueVisitor9<Void, Void>() {
    @Override
    public Void visitString(String text, Void unused) {
        System.out.println("String value: " + text);
        return null;
    }

    @Override
    public Void visitType(
            javax.lang.model.type.TypeMirror type,
            Void unused) {
        System.out.println("Class literal type: " + type);
        return null;
    }
}, null);
~~~

Đây là **một đoạn code minh họa trong processor**, không phải tệp chạy độc lập. Việc dùng visitor giúp xử lý đúng loại dữ liệu mà annotation processor nhận ở compile time.

### Giá trị mặc định cũng là AnnotationValue

**ExecutableElement.getDefaultValue()** và map **getElementValuesWithDefaults(...)** đều làm việc với **AnnotationValue**. Nhờ đó cùng một cơ chế duyệt/diễn giải giá trị có thể dùng cho dữ liệu tường minh và dữ liệu mặc định.

Nhưng default **không nhất thiết đã được sao chép vào metadata ở vị trí sử dụng**. Khi người viết bỏ trống retries, việc thấy retries=3 trong **getElementValuesWithDefaults(...)** không chứng minh mã nguồn của OrderApi có chuỗi **retries=3**.

## 9. Đọc annotation trên declaration và type use đúng vị trí

Cả **Element** lẫn **TypeMirror** trong mô hình ngôn ngữ có thể mang annotation, nhưng vị trí khác nhau:

- **Annotation gắn trên khai báo** class/method/field: thường xét **Element.getAnnotationMirrors()** của khai báo đó.
- **Annotation gắn trên lần sử dụng kiểu (TYPE_USE)**: có thể cần xét **TypeMirror.getAnnotationMirrors()** của vị trí kiểu phù hợp.
- **Annotation trên type parameter declaration**: có thể cần xét **TypeParameterElement** trong danh sách tham số generic của type/method tương ứng.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface Checked {}

class Box<T> {
    java.util.List<@Checked T> items;
}
~~~

**@Checked** ở đây gắn trên **vị trí T là type argument** trong **List<T>**, không phải annotation được khai báo trực tiếp trên class Box. Một processor chỉ gọi **BoxTypeElement.getAnnotationMirrors()** sẽ không tự có một AnnotationMirror đại diện cho dấu @Checked sâu bên trong kiểu field items. Cần duyệt cấu trúc kiểu của field bằng các API compiler model thích hợp.

Khi đã có đúng **AnnotationMirror** trên vị trí cần xử lý, quy tắc **getElementValues()** và **getElementValuesWithDefaults(...)** vẫn giống nhau.

## 10. Khác biệt giữa compiler model và runtime reflection

Hai giai đoạn có thể nhìn cùng khái niệm annotation nhưng với các API khác nhau.

| Mục đích | Compile-time annotation processing | Runtime reflection |
| --- | --- | --- |
| Biểu diễn annotation | **AnnotationMirror** | Đối tượng thực thi interface **Annotation** |
| Biểu diễn class | **TypeElement** và **TypeMirror** | **Class<?>** |
| Giá trị tường minh | **AnnotationMirror.getElementValues()** | API reflection thông thường không cung cấp map riêng của cú pháp tường minh |
| Giá trị có default | **Elements.getElementValuesWithDefaults(...)** | Gọi trực tiếp phương thức phần tử annotation (giá trị hiệu lực) |
| Default được khai báo trên type | **ExecutableElement.getDefaultValue()** | **Method.getDefaultValue()** |
| Retention SOURCE | Processor có thể đọc trong lúc compile source | Không thấy qua reflection sau biên dịch |
| Retention RUNTIME | Processor có thể đọc khi xử lý source | Có thể truy cập annotation runtime |

Chẳng hạn:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Flags {
    boolean active() default true;
}

@Flags
class Client {}
~~~

Ở runtime:

~~~java
Flags f = Client.class.getAnnotation(Flags.class);
System.out.println(f.active()); // true
~~~

Kết quả **true** không tiết lộ tác giả đã viết **active=true** hay bỏ trống: reflection đọc giá trị hiệu lực. Nếu muốn kiểm tra **tường minh so với mặc định ở lúc biên dịch**, AnnotationMirror là mô hình phù hợp.

**Một điểm cần lưu ý khi đọc binary cũ:** Giá trị mặc định của annotation element nằm trên định nghĩa annotation type và có thể thay đổi theo phiên bản thư viện. Vì vậy bản đồ có default phản ánh khai báo kiểu mà công cụ đang thấy; không nên xem nó như bằng chứng rằng tác giả đã nhập giá trị đó ở source.

## 11. Các lỗi thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng getElementValues() luôn trả tất cả phần tử | API chỉ chứa phần tử tường minh | Dùng getElementValuesWithDefaults để lấy bản đầy đủ |
| Thấy retries=3 rồi kết luận người viết đã khai báo retries=3 | Giá trị có thể là default | So map tường minh và map đầy đủ |
| Chỉ so giá trị với default để quyết định có tường minh không | Một giá trị tường minh có thể bằng default | Kiểm tra phần tử có nằm trong getElementValues() không |
| Dùng **Map<String,Object>** trực tiếp với getElementValues() | Key/value của API là ExecutableElement và AnnotationValue | Duyệt/copy rồi chuyển đổi có chủ đích |
| Tưởng getDefaultValue() đọc giá trị của lần sử dụng annotation | Nó đọc default của **khai báo element** | Dùng map của AnnotationMirror để đọc lần sử dụng |
| Cho rằng getDefaultValue() trả null tức annotation vắng mặt | Null chỉ có nghĩa element không khai báo default | Phân biệt kiểu annotation, phần tử và nơi sử dụng |
| Cố cast giá trị Class thành Class<?> trong processor | Compiler model biểu diễn class literal bằng TypeMirror | Xử lý TypeMirror hoặc AnnotationValueVisitor |
| Dùng reflection để phân biệt cú pháp explicit/default từ object annotation | Reflection cung cấp giá trị hiệu lực | Đọc model nguồn bằng annotation processor nếu cần phân biệt |
| Tìm TYPE_USE annotation sâu trong generic bằng getAnnotationMirrors() của class | Annotation gắn trên vị trí kiểu, không phải class declaration | Duyệt TypeMirror đúng vị trí |
| Trông chờ processor chạy mà không được javac cấu hình | Annotation không tự gọi processor | Khai báo -processor/-processorpath hoặc cấu hình build tool |
| Dựa vào thứ tự map do compiler trả về | Thứ tự có thể gây phụ thuộc trình bày/công cụ | Sắp xếp theo tên khi tạo báo cáo ổn định |
| Tạo lại cùng source trong nhiều rounds | Filer không cho tạo cùng path lặp trong một lần processing | Theo dõi trạng thái và xử lý round đúng |
| Đọc SOURCE-retained annotation bằng Class.getAnnotation lúc chạy | SOURCE không được lưu cho reflection | Phân biệt compile-time processing và runtime reflection |

## 12. Quy trình thực tế cho processor cần giá trị cấu hình

Một trình tự kiểm tra rõ ràng:

1. **Lấy Element đúng** từ **RoundEnvironment.getElementsAnnotatedWith(annotationType)** hoặc cấu trúc duyệt compiler model.
2. **Tìm AnnotationMirror đúng kiểu** trong **getAnnotationMirrors()** của Element/TypeMirror liên quan.
3. **Lấy map tường minh** bằng **mirror.getElementValues()** nếu cần biết người viết đã chủ động truyền những element nào.
4. **Lấy map đầy đủ** bằng **elements.getElementValuesWithDefaults(mirror)** nếu cần sinh cấu hình hiệu lực.
5. **Phân tích AnnotationValue theo đúng loại**, dùng getValue()/visitor với class literals, enum, array, nested annotation.
6. **Kiểm tra element bắt buộc và kiểu dữ liệu** theo khai báo; compiler sẽ xử lý quy tắc ngôn ngữ, còn processor có thể bổ sung constraint nghiệp vụ.
7. **Báo diagnostic đúng** qua **Messager**, hoặc sinh source/resource qua **Filer**, không tự giả định thứ tự duyệt hay số rounds.
8. **Viết test compile-time** kiểm tra cả ba trường hợp: bỏ trống element có default, truyền giá trị khác default, truyền tường minh giá trị bằng default.

Cách chọn API phụ thuộc mục tiêu: **“Tác giả có chỉ định không?”** và **“Giá trị hiệu lực là gì?”** là hai câu hỏi độc lập. Không nên sử dụng map chỉ chứa explicit cho một tác vụ yêu cầu cấu hình đầy đủ, cũng không dùng map bao gồm default để suy ngược cú pháp đã gõ.

## 13. Bài tập tự kiểm tra

**Bài 1.** Cho:

~~~java
@interface Cache {
    int ttl() default 60;
    String region() default "global";
}

@Cache
class CacheA {}

@Cache(ttl = 60)
class CacheB {}

@Cache(ttl = 120, region = "eu")
class CacheC {}
~~~

Map explicit và map có default sẽ khác nhau như thế nào?

| Class | getElementValues() | getElementValuesWithDefaults(...) |
| --- | --- | --- |
| **CacheA** | Rỗng | ttl=60; region="global" |
| **CacheB** | ttl=60 | ttl=60; region="global" |
| **CacheC** | ttl=120; region="eu" | ttl=120; region="eu" |

**Đáp án then chốt:** CacheA và CacheB có cùng giá trị **ttl** hiệu lực nhưng khác nhau về việc người viết có nhập **ttl=60** hay không. Map explicit của CacheA rỗng **không có nghĩa @Cache vắng mặt**.

**Bài 2.** Khi **retries()** có **default 3**, **ExecutableElement.getDefaultValue()** trả về gì? Trả một **AnnotationValue** biểu diễn số 3. Nếu **path()** không có default, phương thức này trả **null**.

**Bài 3.** Một element có kiểu **Class<?> target()** và được dùng như **target = String.class**. Trong processor, AnnotationValue.getValue() đại diện giá trị bằng gì? **TypeMirror** mô tả kiểu String, không phải đối tượng **java.lang.Class** giống runtime.

**Bài 4.** Nếu processor đọc một annotation có SOURCE retention, có thể dùng reflection sau khi chương trình chạy để tìm lại annotation đó không? **Không** bằng API reflection chuẩn; SOURCE annotation không được giữ lại trong class file.

**Bài 5.** Nếu tác giả viết **@Endpoint(path = "/orders", retries = 3)** trong khi retries có default 3, map explicit có chứa retries không? **Có**. Việc bằng default không làm biến mất tính tường minh.

**Bài 6.** Vì sao ví dụ sử dụng TreeMap? Để trình bày các khóa theo tên một cách ổn định, không phụ thuộc thứ tự duyệt các entry của map compiler model hoặc việc người viết đảo thứ tự cặp element=value.

## 14. Tài liệu Java chính thức

- **Java SE 17 — AnnotationMirror:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html — **getElementValues()** chỉ chứa element-value tường minh.
- **Java SE 17 — Elements:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html#getElementValuesWithDefaults(javax.lang.model.element.AnnotationMirror) — **getElementValuesWithDefaults(...)** bổ sung default.
- **Java SE 17 — ExecutableElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html#getDefaultValue() — truy vấn default của phần tử annotation.
- **Java SE 17 — AnnotationValue:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html — các dạng giá trị, getValue() và visitor.
- **Java SE 17 — javax.annotation.processing:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html — API processor, rounds và môi trường xử lý.
- **Java Language Specification §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2 — ý nghĩa của default ở mức ngôn ngữ.

**Ghi nhớ:** **getElementValues()** phản ánh **những gì đã được chỉ định tường minh**; **getElementValuesWithDefaults(...)** phản ánh **các giá trị sau khi bổ sung default**; còn **getDefaultValue()** phản ánh **giá trị mặc định khai báo trên chính element của kiểu annotation**. Dùng đúng API giúp annotation processor vừa giữ được ý đồ người viết mã nguồn, vừa tạo ra cấu hình hiệu lực đúng theo Java.
