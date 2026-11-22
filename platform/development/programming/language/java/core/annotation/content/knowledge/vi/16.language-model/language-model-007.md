# Đọc giá trị Class bằng mô hình kiểu và xử lý MirroredTypeException trong Java Annotation Processing

Trong Java, một annotation element có thể trả về `Class<?>` hoặc `Class<?>[]`:

~~~java
@interface LinkedTo {
    Class<?> value();
    Class<?>[] extras() default {};
}
~~~

Khi dùng annotation lúc **chạy ứng dụng**, ta thường mong lấy một object `Class<?>` từ `annotation.value()`. Nhưng khi viết **annotation processor** chạy trong lúc biên dịch bằng `javac`, loại thông tin cần xử lý lại là **mô hình ngôn ngữ Java** — đặc biệt là `TypeMirror` và `TypeElement`. Nếu processor gọi một element kiểu `Class` trên proxy annotation do compiler cung cấp, API có thể ném `MirroredTypeException` để chuyển cho processor **kiểu được mô tả** mà không tải class đó vào JVM của compiler. Với `Class[]`, API tương ứng là `MirroredTypesException`.

Bài này giải thích vì sao exception ở đây là **cơ chế API có chủ đích**, cách xử lý đúng với `TypeMirror`, cách đọc trực tiếp `AnnotationMirror` (thường thích hợp hơn khi xây dựng công cụ), cùng ví dụ Java 17+ thực sự biên dịch và chạy annotation processor.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Phân biệt `java.lang.Class<?>` trong runtime Reflection với `javax.lang.model.type.TypeMirror` trong compile-time language model.
- Giải thích vì sao compiler không nhất thiết tải được class được viết dưới dạng `SomeType.class` trong mã nguồn đang được biên dịch.
- Bắt `MirroredTypeException` khi đọc element `Class<?>` và lấy `TypeMirror` bằng `getTypeMirror()`.
- Bắt `MirroredTypesException` cho `Class<?>[]` và lấy danh sách `TypeMirror` qua `getTypeMirrors()`.
- Đọc annotation qua `Element.getAnnotationMirrors()` / `AnnotationMirror` / `AnnotationValue` mà không cần triệu hồi proxy element trả `Class<?>`.
- Phân biệt `AnnotationMirror.getElementValues()` (giá trị được chỉ định tường minh) với `Elements.getElementValuesWithDefaults()` (bao gồm mặc định).
- Dùng `Types.isSameType(...)`, `Types.isSubtype(...)` và `Types.asElement(...)` đúng hoàn cảnh thay cho so sánh `Class<?>`.
- Chọn đúng chiến lược xử lý kiểu thiếu/chưa phân giải được, type mirror có `TypeKind.ERROR`, và vòng xử lý annotation processing.
- Kiểm chứng một processor `SOURCE` retention bằng hai lệnh `javac --release 17`.

## 2. Hai thế giới: Runtime Reflection và compile-time language model

### 2.1. Lúc runtime: `Class<?>` đại diện cho class đã được môi trường chạy nhận biết

Một chương trình runtime có thể khai báo:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Handler {
    Class<?> value();
}

@Handler(String.class)
class RuntimeExample {}
~~~

Nếu annotation được giữ ở retention `RUNTIME` và class liên quan tải được, có thể truy vấn:

~~~java
Class<?> clazz = RuntimeExample.class
        .getAnnotation(Handler.class)
        .value();

System.out.println(clazz.getName()); // java.lang.String
~~~

Hai khối trên là những đoạn cùng ngữ cảnh minh họa; đặt chúng vào một file hợp lệ hoặc IDE khi thực hành. Runtime Reflection làm việc với class objects đã được JVM hiểu theo cơ chế loading/linking. Trên đối tượng `Class<?>`, bạn có thể lấy tên, superclass, method, field theo API Reflection.

### 2.2. Lúc biên dịch: compiler mô hình hóa type trước khi chương trình chạy

Annotation processor triển khai `javax.annotation.processing.Processor`, thường kế thừa `AbstractProcessor`. Nó nhận các đối tượng thuộc Java Language Model:

| Vai trò | API chính |
| --- | --- |
| Một khai báo như class/interface/method/field | `javax.lang.model.element.Element` |
| Khai báo một kiểu class/interface | `TypeElement` |
| Một **kiểu** trong chương trình đang biên dịch | `TypeMirror` |
| Một annotation xuất hiện trên khai báo | `AnnotationMirror` |
| Một element value của annotation | `AnnotationValue` |
| Tiện ích làm việc với kiểu | `processingEnv.getTypeUtils()`, giao diện `Types` |
| Tiện ích làm việc với khai báo và annotation | `processingEnv.getElementUtils()`, giao diện `Elements` |

Ví dụ nguồn có:

~~~java
@LinkedTo(java.util.List.class)
public class Example {}
~~~

Compiler cần biết đây là tham chiếu đến **kiểu `java.util.List`**, nhưng việc tạo một object `Class<java.util.List>` không phải giao diện trung tâm của mô hình nguồn. Quan trọng hơn, type được tham chiếu có thể là một class **đang được biên dịch**, được sinh ở round sau, hoặc chưa sẵn sàng để nạp bằng class loader của processor.

Vì thế trong processor, câu hỏi phù hợp thường là **“kiểu nào được tham chiếu, có quan hệ kiểu nào?”**, không phải **“làm sao gọi `Class.forName` để tải nó?”**.

## 3. `MirroredTypeException`: một tín hiệu chuyển từ `Class` sang `TypeMirror`

API `javax.lang.model.element.Element.getAnnotation(Class<A>)` có thể cung cấp một proxy theo interface của annotation type. Nếu annotation đó có element trả về `Class`, việc gọi element trong ngữ cảnh compile-time có thể ném:

~~~java
javax.lang.model.type.MirroredTypeException
~~~

Đây là một unchecked exception, có method:

~~~java
TypeMirror mirror = exception.getTypeMirror();
~~~

`TypeMirror` trả về là mô hình của kiểu mà annotation khai báo, ví dụ `java.util.List`. Thay vì coi exception là “hỏng processor”, trong trường hợp này **processor nên khai thác kiểu được gửi kèm exception**.

Mẫu chuẩn:

~~~java
LinkedTo annotation = element.getAnnotation(LinkedTo.class);

TypeMirror referencedType;
try {
    annotation.value(); // Class<?>: trong processor sẽ ném MirroredTypeException.
    throw new AssertionError("Expected MirroredTypeException in this processor");
} catch (MirroredTypeException exception) {
    referencedType = exception.getTypeMirror();
}
~~~

Mẫu trên giả định đang ở trong processor, `element` hợp lệ, `LinkedTo` và `MirroredTypeException` đã được import. Vì đây là cách kiểm chứng hành vi annotation proxy của compiler đang dùng, đoạn có `AssertionError` thích hợp cho **ví dụ học tập**; thư viện production nên chọn API language model phù hợp và không nhất thiết coi mọi implementation trả được `Class` là lỗi.

Chú ý:

- `MirroredTypeException` chứa **`TypeMirror`**, không chứa `Class<?>`.
- `getTypeMirror()` có thể trả `null` nếu exception đã được serialize/deserialze theo hợp đồng của API; thông thường processor nhận exception trực tiếp sẽ có mirror.
- Không cần `Class.forName(...)` để khôi phục kiểu; đó là bước sai hướng nếu bạn chỉ muốn kiểm tra type metadata.
- `TypeMirror.toString()` có thể cho tên hiển thị hữu ích như `java.util.List`, nhưng đừng coi chuỗi đó là cơ sở duy nhất cho mọi phép kiểm tra quan hệ kiểu.

### Vì sao không nên cố gọi `annotation.value().getName()`?

Đoạn:

~~~java
String name = annotation.value().getName();
~~~

trông tự nhiên nhưng khi xử lý source có thể ném `MirroredTypeException` **ngay tại lời gọi `annotation.value()`**; phần `getName()` không được thực hiện. Mở rộng catch sang toàn đoạn vẫn có thể đọc type mirror, nhưng giải pháp sáng sủa hơn là đọc `TypeMirror` một cách chủ đích.

Trong processor, class của annotation type (`LinkedTo.class`) phải sẵn có với processor để gọi `getAnnotation(LinkedTo.class)`; điều đó **không** đồng nghĩa class **được tham chiếu trong element `value()`** đã sẵn có để tải.

## 4. `MirroredTypesException` dành cho `Class<?>[]`

Nếu annotation khai báo một mảng class literals:

~~~java
@interface Dependencies {
    Class<?>[] value();
}
~~~

Và người dùng viết:

~~~java
@Dependencies({String.class, Runnable.class})
class ExampleDependencies {}
~~~

Thì khi processor đọc `annotation.value()` có thể ném **`MirroredTypesException`**, với:

~~~java
List<? extends TypeMirror> types =
        exception.getTypeMirrors();
~~~

So sánh:

| Giá trị element | Exception compile-time | API lấy language model |
| --- | --- | --- |
| `Class<?> clazz()` | `MirroredTypeException` | `getTypeMirror()` |
| `Class<?>[] classes()` | `MirroredTypesException` | `getTypeMirrors()` |

`MirroredTypeException` **kế thừa** `MirroredTypesException`, vì vậy khi có những nhánh catch cùng lúc, phải để nhánh subclass trước superclass. Với hai element khác nhau như trong ví dụ chính, ta bắt chúng trong **hai khối `try` riêng** để không có xung đột.

Mẫu:

~~~java
List<? extends TypeMirror> types;
try {
    annotation.extras();
    throw new AssertionError("Expected MirroredTypesException");
} catch (MirroredTypesException exception) {
    types = exception.getTypeMirrors();
}
~~~

Đây là ví dụ mục tiêu compile-time. Trong runtime Reflection của ứng dụng bình thường, đọc `Class<?>[]` thường trả mảng class objects khi các class có thể được tải.

Một mảng annotation có thể được viết dạng ngắn một phần tử tại nơi sử dụng, nhưng **kiểu trả về vẫn là `Class<?>[]`** và trong annotation processing tương ứng với danh sách các type mirrors; đừng vì cú pháp ngắn mà xử lý nó như một `Class<?>` đơn.

## 5. Ví dụ Java 17+ hoàn chỉnh, kiểm chứng cả proxy lẫn AnnotationMirror

Ta xây một processor có ba file trong package `demo`. Annotation đích có retention `SOURCE` để minh họa: **annotation processing không cần retention `RUNTIME`**. Compiler phân tích annotation ngay khi biên dịch source.

Cấu trúc thư mục:

~~~text
src/
  demo/
    LinkedTo.java
    LinkProcessor.java
    Example.java
build/           (thư mục output cho .class)
~~~

### 5.1. `src/demo/LinkedTo.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface LinkedTo {
    Class<?> value();

    Class<?>[] extras() default {
        String.class, Runnable.class
    };
}
~~~

`value()` bắt buộc, còn `extras()` có mặc định hai class literals. Chú ý phần tử annotation kiểu `Class<?>` được dùng **để tham chiếu type**; không có code nào sẽ tạo instance `String` hay `Runnable` từ các literal này.

### 5.2. `src/demo/LinkProcessor.java`

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

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
import javax.lang.model.type.MirroredTypeException;
import javax.lang.model.type.MirroredTypesException;
import javax.lang.model.type.TypeMirror;

@SupportedAnnotationTypes("demo.LinkedTo")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class LinkProcessor extends AbstractProcessor {

    @Override
    public boolean process(Set<? extends TypeElement> types,
                           RoundEnvironment round) {

        for (Element element :
                round.getElementsAnnotatedWith(LinkedTo.class)) {

            // Cách 1: proxy annotation + exception có TypeMirror.
            LinkedTo annotation =
                    element.getAnnotation(LinkedTo.class);

            TypeMirror single;
            List<? extends TypeMirror> multiple;

            try {
                annotation.value();
                throw new AssertionError(
                        "Class loaded unexpectedly in this demo");
            } catch (MirroredTypeException exception) {
                single = exception.getTypeMirror();
            }

            try {
                annotation.extras();
                throw new AssertionError(
                        "Class array loaded unexpectedly in this demo");
            } catch (MirroredTypesException exception) {
                multiple = exception.getTypeMirrors();
            }

            System.out.println("proxySingle=" + single);
            System.out.println("proxyArray=" +
                    multiple.stream()
                            .map(Object::toString)
                            .collect(Collectors.joining(",")));

            // Cách 2: đọc mô hình annotation trực tiếp, không gọi Class.
            for (AnnotationMirror mirror :
                    element.getAnnotationMirrors()) {

                if (!mirror.getAnnotationType()
                        .toString().equals("demo.LinkedTo")) {
                    continue;
                }

                Map<? extends ExecutableElement,
                        ? extends AnnotationValue> explicit =
                        mirror.getElementValues();

                Map<? extends ExecutableElement,
                        ? extends AnnotationValue> withDefaults =
                        processingEnv.getElementUtils()
                                .getElementValuesWithDefaults(mirror);

                System.out.println("explicit=" + explicit.size()
                        + ",withDefaults=" + withDefaults.size());

                for (var entry : withDefaults.entrySet()) {
                    String key = entry.getKey().getSimpleName().toString();

                    if (key.equals("value")) {
                        TypeMirror fromMirror =
                                (TypeMirror) entry.getValue().getValue();

                        System.out.println("mirrorSingle=" + fromMirror);
                        System.out.println("sameType=" +
                                processingEnv.getTypeUtils()
                                        .isSameType(single, fromMirror));
                    } else if (key.equals("extras")) {
                        @SuppressWarnings("unchecked")
                        List<? extends AnnotationValue> array =
                                (List<? extends AnnotationValue>)
                                        entry.getValue().getValue();

                        System.out.println("mirrorArray=" +
                                array.stream()
                                        .map(item ->
                                                item.getValue().toString())
                                        .collect(Collectors.joining(",")));
                    }
                }
            }
        }
        return true;
    }
}
~~~

Mã dùng `var` cho biến cục bộ trong vòng lặp (hợp lệ từ Java 10) và `Collectors.joining(...)` để ghép các tên theo đúng thứ tự xuất hiện trong mảng. Processor tự động được môi trường `javac` khởi tạo; người học không cần viết `main` cho processor.

**Lưu ý về `AssertionError`:** đây là phép kiểm tra cố ý trong **fixture thử nghiệm của javac** để xác nhận đường đi qua exception. Trong processor phải hỗ trợ nhiều implementation, nên ưu tiên đường `AnnotationMirror` hoặc thiết kế fallback thích hợp thay vì trông chờ mọi implementation đều ném một exception duy nhất theo đúng cách giống ví dụ.

### 5.3. `src/demo/Example.java`

~~~java
package demo;

@LinkedTo(java.util.List.class)
public class Example {}
~~~

`Example` chỉ ghi tường minh `value()`. Element `extras()` không xuất hiện trong dòng `@LinkedTo` nên nhận mặc định `{String.class, Runnable.class}`.

### 5.4. Biên dịch và thực thi processing

Tạo thư mục `build` rồi chạy ở thư mục chứa `src`:

~~~bash
mkdir -p build

javac --release 17 -proc:none -d build \
  src/demo/LinkedTo.java src/demo/LinkProcessor.java

javac --release 17 -cp build -processorpath build \
  -processor demo.LinkProcessor -d build \
  src/demo/Example.java
~~~

Dấu `\` nối dòng là cú pháp shell Bash/POSIX. Trên Windows PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force build` hoặc `mkdir build`, và viết mỗi lệnh `javac` trên một dòng:

~~~powershell
javac --release 17 -proc:none -d build src/demo/LinkedTo.java src/demo/LinkProcessor.java
javac --release 17 -cp build -processorpath build -processor demo.LinkProcessor -d build src/demo/Example.java
~~~

- Lệnh đầu biên dịch annotation type và processor class, với `-proc:none` để tránh chạy processor trong lúc đang xây processor.
- `-cp build` cho compiler tìm thấy `demo.LinkedTo` ở lần biên dịch source đích.
- `-processorpath build` cho compiler tìm `demo.LinkProcessor`; dùng `-processor` để chọn nó tường minh.
- `--release 17` đảm bảo mã tương thích với mức ngôn ngữ và API Java 17. Processor chạy trong JVM của compiler chứ không chạy bằng lệnh `java Example`.
- `-d build` ghi class files vào thư mục build; không có file nguồn sinh thêm trong demo.

**Kết quả in ra khi lệnh `javac` thứ hai chạy:**

~~~text
proxySingle=java.util.List
proxyArray=java.lang.String,java.lang.Runnable
explicit=1,withDefaults=2
mirrorSingle=java.util.List
sameType=true
mirrorArray=java.lang.String,java.lang.Runnable
~~~

Các dòng này đã được biên dịch và kiểm chứng với `javac --release 17` trên JDK hiện đại.

### 5.5. Phân tích kết quả

1. `proxySingle=java.util.List`: khi processor gọi `annotation.value()`, `MirroredTypeException` đưa lại `TypeMirror` cho `java.util.List`.
2. `proxyArray=java.lang.String,java.lang.Runnable`: `MirroredTypesException` đưa ra danh sách mirror theo thứ tự các giá trị mặc định của `extras()`.
3. `explicit=1,withDefaults=2`: người viết `@LinkedTo` chỉ cung cấp `value`; `AnnotationMirror.getElementValues()` có một entry. `Elements.getElementValuesWithDefaults(...)` bổ sung `extras` thành hai entries.
4. `mirrorSingle=java.util.List`: giá trị của element kiểu `Class` trong mô hình annotation là `TypeMirror`, không phải `Class<?>`.
5. `sameType=true`: `Types.isSameType(single, fromMirror)` so sánh hai type mirrors và xác nhận chúng biểu diễn cùng kiểu.
6. `mirrorArray=java.lang.String,java.lang.Runnable`: `AnnotationValue.getValue()` của mảng là danh sách `AnnotationValue`; từng phần tử có giá trị là `TypeMirror`.

Không cần nạp `java.util.List` qua `Class.forName`; processor chỉ làm việc với mô hình kiểu. Ví dụ cũng cho thấy `SOURCE` retention vẫn dùng được trong annotation processing.

## 6. Cách đọc `AnnotationMirror` mà không dùng exception

Mặc dù catch `MirroredTypeException` là kỹ thuật hợp lệ và hữu ích khi đã có proxy annotation, **truy cập trực tiếp mô hình ngôn ngữ** thường phù hợp hơn trong một processor tổng quát hoặc khi xử lý annotation mà processor không có interface của nó ở compile classpath.

### 6.1. Bước 1 — tìm annotation mirror cần thiết

~~~java
for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    if (mirror.getAnnotationType().toString()
            .equals("demo.LinkedTo")) {
        // Đã tìm thấy annotation đích.
    }
}
~~~

Đây là đoạn code **trong processor**. `AnnotationMirror.getAnnotationType()` trả `DeclaredType` của annotation, giúp ta biết annotation nào đang được biểu diễn.

So sánh tên đầy đủ bằng `toString()` là cách đơn giản trong demo. Với processor lớn, có thể dùng `TypeElement` được lấy từ `Elements.getTypeElement("demo.LinkedTo")` và so sánh kiểu bằng `Types.isSameType(...)`, hoặc so sánh `TypeElement.getQualifiedName()` để tránh phụ thuộc vào string formatting.

### 6.2. Bước 2 — quyết định có cần default values hay không

~~~java
Map<? extends ExecutableElement, ? extends AnnotationValue> explicit =
        mirror.getElementValues();

Map<? extends ExecutableElement, ? extends AnnotationValue> complete =
        processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
~~~

Sự khác biệt:

| API | Có chứa phần tử default nếu không ghi tại nơi sử dụng? |
| --- | --- |
| `AnnotationMirror.getElementValues()` | **Không**; chỉ chứa các element values ghi tường minh |
| `Elements.getElementValuesWithDefaults(mirror)` | **Có**; trả values cùng defaults cho các element cần thiết |

Nếu muốn biết người viết source đã ghi tường minh cái gì, chọn `getElementValues()`. Nếu muốn đọc cấu hình **hiệu lực đầy đủ** để validate/generate code, thường chọn `getElementValuesWithDefaults()`.

Các key của map là `ExecutableElement` mô tả các annotation elements như `value()` và `extras()`, **không phải chuỗi key trực tiếp**. Mã ví dụ đổi key thành tên bằng `entry.getKey().getSimpleName().toString()`.

### 6.3. Bước 3 — hiểu kiểu dữ liệu từ `AnnotationValue.getValue()`

API `AnnotationValue.getValue()` trả `Object`, nhưng giá trị thực nằm trong một tập kiểu đã được đặc tả:

| Kiểu annotation element | Giá trị nhận qua model |
| --- | --- |
| `int`, `boolean`, `long`... | Wrapper như `Integer`, `Boolean`, `Long` |
| `String` | `String` |
| `Class<?>` hoặc `Class<? extends X>` | `TypeMirror` |
| Enum element | `VariableElement` đại diện enum constant |
| Annotation lồng nhau | `AnnotationMirror` |
| Mảng, bao gồm `Class<?>[]` | `List<? extends AnnotationValue>`, mỗi phần tử là một model value |

Với một `Class<?>`:

~~~java
TypeMirror type =
        (TypeMirror) entry.getValue().getValue();
~~~

Với `Class<?>[]`:

~~~java
@SuppressWarnings("unchecked")
List<? extends AnnotationValue> values =
        (List<? extends AnnotationValue>)
                entry.getValue().getValue();

for (AnnotationValue value : values) {
    TypeMirror type = (TypeMirror) value.getValue();
    System.out.println(type);
}
~~~

Hai đoạn trên là **mảnh code minh họa trong processor**, giả sử biến `entry` được tạo từ map ở trên. Mảng được mô hình hóa thành danh sách `AnnotationValue`, **không** phải `List<TypeMirror>` ở cấp ngoài và cũng không phải `Class<?>[]`.

Nếu muốn code xử lý toàn bộ các kiểu annotation value một cách chặt chẽ, xem `AnnotationValueVisitor` / `SimpleAnnotationValueVisitor*` thay vì ép kiểu dựa vào tên element; với annotation type đã biết, ép kiểu phù hợp như trong demo vẫn dễ học và trực tiếp.

## 7. Dùng `TypeMirror` đúng cách trong compiler

### 7.1. `TypeMirror` không phải `Class<?>`

Hai kiểu object phục vụ hai mục đích khác nhau:

| Thuộc tính | `Class<?>` | `TypeMirror` |
| --- | --- | --- |
| Thế giới chính | JVM/runtime Reflection | Compile-time language model |
| Đại diện cho | Class được hệ thống runtime nhận biết | Kiểu Java mà compiler đang mô hình hóa |
| Phụ thuộc tải class | Có thể cần class loading | Không phải thao tác class loading |
| Phân tích quan hệ kiểu | `isAssignableFrom(...)` trên class | `Types.isAssignable(...)`, `isSubtype(...)`, `isSameType(...)` |
| Lấy khai báo | Reflection class/method/field | `Types.asElement(...)`, `TypeElement` và language-model elements |
| Dùng trong annotation processor | Tránh dùng cho các type nguồn đang compile | Phù hợp với model do compiler quản lý |

Mặc dù `TypeMirror.toString()` thường biểu diễn tên đủ rõ, ứng dụng cần **kiểm tra ngữ nghĩa kiểu** nên dùng `Types` thay cho so sánh chuỗi.

Ví dụ:

~~~java
Types typeUtils = processingEnv.getTypeUtils();
boolean same = typeUtils.isSameType(left, right);
boolean compatible = typeUtils.isAssignable(left, right);
boolean subclassOrSame =
        typeUtils.isSubtype(left, right);
~~~

`left` và `right` phải là những `TypeMirror` hợp lệ do môi trường xử lý cung cấp. `isSameType` kiểm tra tương đương type; `isAssignable` xét khả năng gán kiểu; `isSubtype` xét quan hệ subtype. Ba câu hỏi này **không phải cùng một phép thử**.

### 7.2. Lấy `TypeElement` khi value trỏ đến class/interface

Nếu muốn lấy **khai báo** của một kiểu:

~~~java
Element typeElement =
        processingEnv.getTypeUtils().asElement(typeMirror);

if (typeElement instanceof TypeElement declaration) {
    System.out.println(declaration.getQualifiedName());
}
~~~

Với mirror đại diện cho một **declared class/interface type** như `java.util.List`, `asElement(...)` có thể trả `TypeElement` để bạn kiểm tra tên, modifier, các method được khai báo, v.v.

Nhưng không phải mọi `TypeMirror` đều đại diện cho declared type:

- `int.class` mô tả primitive type, không có class declaration `TypeElement` tương ứng.
- `String[].class` mô tả array type, có thể cần xét `ArrayType.getComponentType()`.
- `void.class` (ở nơi Java cho phép) liên quan đến pseudo-type.
- Type chưa được phân giải hoàn toàn có thể biểu hiện dưới dạng `ErrorType` / `TypeKind.ERROR`.

Vì vậy cần kiểm tra `mirror.getKind()` và kết quả `asElement(...)` trước khi cast. Đừng mặc định annotation element kiểu `Class<?>` đồng nghĩa mirror luôn có `TypeKind.DECLARED`.

### 7.3. So sánh với một kiểu khác trong compilation environment

Ví dụ cần kiểm tra kiểu được đánh dấu có tương thích `java.lang.Runnable`:

~~~java
TypeElement runnableElement =
        processingEnv.getElementUtils()
                .getTypeElement("java.lang.Runnable");

if (runnableElement != null) {
    TypeMirror runnableType = runnableElement.asType();
    boolean compatible = processingEnv.getTypeUtils()
            .isAssignable(typeMirror, runnableType);
}
~~~

Nếu `typeMirror` là kiểu có thể gán được vào `Runnable`, `compatible` là `true`. Đừng thay câu hỏi này bằng `typeMirror.toString().contains("Runnable")` vì kiểm tra chuỗi không hiểu subtype, interface implementation hay generic type relations.

Khi cần so sánh **cùng kiểu** bất kể cách tham chiếu, `isSameType` phù hợp hơn. Với generics, hãy cân nhắc erasure và parameterization tùy mục đích, thay vì tự loại bỏ `<...>` bằng xử lý text.

### 7.4. Type chưa giải quyết được và generated sources

Annotation processors thường chạy qua **nhiều vòng**; có thể gặp kiểu chưa đầy đủ hoặc class sẽ được một processor khác tạo ra. Tùy compiler/trạng thái nguồn, một `TypeMirror` có thể là `ErrorType`. Lúc đó:

- Đừng gọi `Class.forName(...)` để “cứu” một kiểu chưa có.
- Kiểm tra `getKind() == TypeKind.ERROR` khi cần và viết diagnostic rõ ràng.
- Nếu quy trình cho phép, xử lý lại thông tin ở round sau khi các file đã được sinh/giải quyết.
- Tránh lưu `TypeMirror`/`Element` trong cache kéo dài ngoài môi trường xử lý mà chúng được cung cấp, đặc biệt qua những vòng hoặc lần compile khác nhau mà không hiểu rõ hợp đồng API.

Người dùng processor cần diagnostics hữu ích như "loại được tham chiếu chưa thể phân giải", không phải stacktrace của một thao tác class loading vốn không cần thiết.

## 8. Giá trị mặc định `Class` và khác biệt giữa hai API

Cho khai báo:

~~~java
@interface Strategy {
    Class<?> primary();
    Class<?>[] fallback() default {String.class};
}
~~~

Và usage:

~~~java
@Strategy(primary = java.util.Map.class)
class Configuration {}
~~~

**Nếu đọc qua proxy annotation** trong processor, lời gọi `primary()` có thể dẫn tới `MirroredTypeException`; lời gọi `fallback()` có thể dẫn tới `MirroredTypesException` ngay cả khi giá trị không được ghi tại usage, vì proxy cung cấp giá trị hiệu lực gồm defaults.

**Nếu đọc qua `AnnotationMirror`**, `getElementValues()` thường chỉ có `primary` vì `fallback` bị lược bỏ tại chỗ sử dụng. Dùng `Elements.getElementValuesWithDefaults()` để nhận cả hai.

Do đó có hai loại yêu cầu khác nhau:

- **Theo dõi source người dùng đã ghi gì**: dùng map từ `getElementValues()`.
- **Lấy cấu hình hiệu lực**: dùng `getElementValuesWithDefaults()`, rồi đọc đúng model value kiểu `TypeMirror` hoặc danh sách các `AnnotationValue`.

Không nên chuyển annotation type thành retention `RUNTIME` chỉ để lấy `Class<?>` trong processor. Retention mô tả thời gian giữ annotation; nó không thay đổi bản chất **compile-time language model** của processor.

## 9. Khi nào dùng cách catch exception, khi nào dùng AnnotationMirror?

**Cách A — gọi annotation proxy và catch `MirroredTypeException`:**

Phù hợp khi processor **đã biết trước annotation type ở compile time** và code hiện tại dùng `element.getAnnotation(MyAnnotation.class)` để đọc các element khác (chuỗi, số, enum). Cách này ngắn cho một số trường hợp, nhưng cần xử lý `Class` và `Class[]` bằng exception đặc biệt.

**Cách B — đọc `AnnotationMirror`:**

Phù hợp khi viết **processor tổng quát**, validator công cụ, khi cần giữ lại cấu trúc nguồn hay nhận biết giá trị **explicit/default**, khi annotation type không nằm trực tiếp trên compile classpath của mã processor hoặc khi muốn tránh proxy methods có kết quả kiểu `Class`. Cách này tương thích tư duy language model và dễ mở rộng sang enum/nested annotation/array elements.

Không có yêu cầu tất cả công cụ phải dùng một cách. Điều quan trọng là **đừng cố tải lớp đích chỉ để biết kiểu của nó tại compile time**.

Một số lỗi thường gặp khi tự viết xử lý:

- Bắt `ClassNotFoundException` thay cho `MirroredTypeException`. Trong proxy path này, exception trọng tâm là `MirroredTypeException` hoặc `MirroredTypesException`, không phải một thất bại thông thường của `Class.forName`.
- Nhầm `MirroredTypeException` với `TypeNotPresentException` trong những ngữ cảnh runtime khác. Hãy xem chính xác API bạn đang gọi và compiler/proxy đang cung cấp gì.
- Gọi `annotation.value().getCanonicalName()` bên trong `try` mà không hiểu exception được ném **trước** lời gọi `getCanonicalName()`.
- Ép `AnnotationValue.getValue()` thẳng thành `Class<?>`: trong language model, đối với class literal nó là `TypeMirror`.
- Ép giá trị mảng trực tiếp thành `List<TypeMirror>`: tầng ngoài là `List<? extends AnnotationValue>`.
- Lọc annotation bằng simple name `"LinkedTo"` trong một dự án nhiều package; hai annotation types khác nhau có thể trùng simple name.
- Quên default values và tưởng `getElementValues().size() == 1` đồng nghĩa annotation chỉ có một element.
- Dùng `TypeMirror.toString()` làm kết quả cuối cho kiểm tra subtype/generic; dùng `Types` để làm kiểm tra kiểu có ngữ nghĩa.
- Cố giữ `TypeMirror` qua các lần chạy compiler rồi so sánh như một kiểu runtime bất biến toàn cục; model thuộc về môi trường compilation.

## 10. Các trường hợp cần cân nhắc kỹ

### 10.1. Primitive, array và `void.class`

Một annotation element kiểu `Class<?>` có thể chứa `int.class`, `String[].class` hoặc `void.class` ở vị trí Java cho phép. Khi lấy `TypeMirror`, đừng mặc định nó là một `DeclaredType` có `TypeElement`. Hãy xét `TypeKind` hoặc xử lý bằng `TypeVisitor` phù hợp.

Nếu chỉ cần loại kiểu để báo diagnostics, `getKind()` và `toString()` có thể đã đủ; nếu cần quan hệ kiểu hoặc khai báo, dùng APIs tương ứng.

### 10.2. `Class<? extends Interface>` vẫn cho model type

Ví dụ:

~~~java
@interface HandlerType {
    Class<? extends Runnable> value();
}
~~~

Compiler kiểm tra type literal có tương thích bound `Runnable` theo quy tắc của Java. Trong processor, element type vẫn là một `Class`-valued annotation member và model tương ứng vẫn nên được xử lý qua `TypeMirror`. `Types.isAssignable(...)` cho phép kiểm tra tương thích khi cần xác nhận thêm quy tắc của công cụ.

### 10.3. Nested annotation có chứa `Class`

Một annotation element có thể trả về annotation lồng nhau:

~~~java
@interface Inner {
    Class<?> type();
}

@interface Outer {
    Inner nested();
}
~~~

Nếu dùng proxy, thao tác `outer.nested().type()` có thể ném `MirroredTypeException` tại member `type()`. Nếu dùng mô hình, giá trị `nested` của `AnnotationValue` là **`AnnotationMirror`**, rồi `type` bên trong chứa **`TypeMirror`**. Mô hình hóa nested annotations theo cấu trúc giúp giảm các giả định runtime.

### 10.4. Arrays và thứ tự

Với `Class<?>[]`, thứ tự khai báo là thông tin có thể quan trọng. `MirroredTypesException.getTypeMirrors()` và danh sách `AnnotationValue` đại diện cho các element mảng theo thứ tự. Đừng chuyển sang `Set<String>` nếu nghiệp vụ cần giữ thứ tự hoặc cho phép các giá trị trùng nhau.

### 10.5. Tính portable và môi trường build

Ví dụ thực thi với `javac` chuẩn. Công cụ dựa trên Java Compiler API, IDE hoặc incremental compiler có thể khác về cách phát hiện processor, cách hiển thị stdout/diagnostics và thứ tự các vòng xử lý. Đừng thiết kế code đòi hỏi một class loader cụ thể hay dựa trên chuỗi hiển thị khi API `TypeMirror`/`Types` có chức năng trực tiếp.

## 11. Bài tập thực hành theo cấp độ

1. **Single Class:** Chạy chương trình ba file. Thay `@LinkedTo(java.util.List.class)` bằng `@LinkedTo(java.util.Map.class)` và dự đoán dòng `proxySingle`, `mirrorSingle`, `sameType`.
2. **Class array:** Ghi đè `extras = {Thread.class, Exception.class}` trong `Example`. Dự đoán vì sao `explicit=2,withDefaults=2` nhưng hai đường đọc array đều cho hai kiểu mới.
3. **Default value:** Xóa toàn bộ tham số `extras` tại usage, kiểm tra `AnnotationMirror.getElementValues()` thiếu `extras` nhưng `Elements.getElementValuesWithDefaults()` không thiếu.
4. **Câu hỏi exception:** Bỏ `try/catch` của `annotation.value()`, để compiler chạy và quan sát stacktrace. Khôi phục code rồi giải thích vì sao đây không phải `ClassNotFoundException`.
5. **Types API:** Lấy `TypeElement` của `java.util.Collection`, rồi dùng `Types.isAssignable(single, collection.asType())` khi `single` trỏ `java.util.List`. Dự đoán kết quả và giải thích quan hệ interface.
6. **Primitive:** Thử `@LinkedTo(int.class)`. Quan sát `TypeMirror.getKind()` và giải thích vì sao không nên cast `Types.asElement(...)` thành `TypeElement` vô điều kiện.
7. **Array type:** Thử `@LinkedTo(String[].class)`. Dùng `TypeKind.ARRAY` và `ArrayType.getComponentType()` để biết type phần tử.
8. **Nested model:** Tạo `@interface Inner { Class<?> clazz(); }` và `@interface Outer { Inner child(); }`, gắn lên class. Duyệt từ `AnnotationMirror` đến `AnnotationValue` của `child` rồi vào model annotation lồng, đọc class literal dưới dạng `TypeMirror`.
9. **Visitor:** Thay các `instanceof`/cast bằng `AnnotationValueVisitor` có nhánh `visitType` và `visitArray`. Viết tests cho `Class<?>`, `Class<?>[]` và `String`.
10. **Diagnostic:** Thay `System.out.println` bằng `processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE, ...)` và chỉ ra cách compiler/IDE hiển thị thông điệp trên source element đang được xử lý.
11. **Source-level behavior:** Đổi retention của `LinkedTo` từ `SOURCE` sang `CLASS` hoặc `RUNTIME`. Kiểm tra compile-time processor vẫn có thể nhìn thấy annotation và thảo luận riêng về Reflection runtime.
12. **Multi-round:** Tạo một processor khác sinh class trong round đầu và một annotation tham chiếu đến class phù hợp. Quan sát các trạng thái type resolution/rounds và áp dụng `TypeKind.ERROR` cùng chiến lược diagnostics thay vì class loading.

## 12. Bảng ghi nhớ nhanh

| Câu hỏi | Kết luận |
| --- | --- |
| `Class<?>` value trong annotation processor có nên đọc như Reflection runtime không? | Không mặc định; ưu tiên mô hình `TypeMirror` |
| Gọi `Class<?> value()` trên annotation proxy có thể xảy ra gì? | `MirroredTypeException` |
| Lấy type sau exception bằng gì? | `getTypeMirror()` |
| Gọi `Class<?>[] extras()` có thể xảy ra gì? | `MirroredTypesException` |
| Lấy danh sách type sau exception bằng gì? | `getTypeMirrors()` |
| Muốn tránh proxy exception? | Duyệt `AnnotationMirror` / `AnnotationValue` |
| `AnnotationValue.getValue()` của class literal là gì? | `TypeMirror` |
| `AnnotationValue.getValue()` của Class array là gì? | `List<? extends AnnotationValue>`, mỗi item chứa `TypeMirror` |
| `getElementValues()` có tự gồm defaults không? | Không |
| API gồm defaults? | `Elements.getElementValuesWithDefaults(...)` |
| So sánh hai kiểu trong compiler bằng gì? | `Types.isSameType(...)` hoặc API quan hệ kiểu khác |
| Cần retention `RUNTIME` để xử lý annotation lúc compile? | Không; `SOURCE` vẫn được annotation processor đọc |
| `Class.forName` có nên là bước bắt buộc? | Không; việc tải class không phải mục tiêu của language model |

**Kết luận:** Annotation elements kiểu `Class` biểu thị **thông tin về kiểu**, nhưng **runtime `Class<?>`** và **compile-time `TypeMirror`** thuộc hai mô hình khác nhau. `MirroredTypeException` / `MirroredTypesException` chính là cây cầu khi bạn chọn đường đọc qua annotation proxy. Khi cần kiểm soát defaults, nested structures hoặc làm việc trực tiếp với ngôn ngữ Java đang biên dịch, `AnnotationMirror` cùng `AnnotationValue` và `Elements/Types` là lựa chọn rõ ràng, an toàn và dễ mở rộng hơn.

### Tài liệu tham khảo

- [Java SE 17 — MirroredTypeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/MirroredTypeException.html).
- [Java SE 17 — MirroredTypesException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/MirroredTypesException.html).
- [Java SE 17 — Element.getAnnotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html).
- [Java SE 17 — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
- [Java SE 17 — AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html).
- [Java SE 17 — AnnotationValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html).
- [Java SE 17 — Elements.getElementValuesWithDefaults](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html#getElementValuesWithDefaults(javax.lang.model.element.AnnotationMirror)).
- [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html).
- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html).
