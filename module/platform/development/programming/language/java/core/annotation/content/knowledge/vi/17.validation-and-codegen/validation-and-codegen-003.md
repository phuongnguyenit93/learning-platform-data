# Gắn chẩn đoán vào khai báo, annotation hoặc phần tử cụ thể trong Java Annotation Processing

## 1. Mục tiêu: thông báo đúng lỗi và đúng chỗ trong mã nguồn

Khi viết **annotation processor** bằng Java, phát hiện cấu hình sai mới chỉ là một nửa nhiệm vụ. Nửa còn lại là báo lỗi để người lập trình biết **khai báo nào**, **annotation nào** và, nếu có thể, **giá trị phần tử nào** cần sửa.

Ví dụ:

```java
@Endpoint(path = "", retries = -1)
class OrderService {}
```

Một thông báo chung như `Invalid annotation` không chỉ rõ người dùng phải sửa `path` hay `retries`. Java SE cung cấp **`javax.annotation.processing.Messager`** với nhiều overload của `printMessage` để gắn diagnostic vào những mức vị trí khác nhau:

- **`Element`**: một khai báo trong mô hình ngôn ngữ, ví dụ class, method, field hoặc parameter.
- **`AnnotationMirror`**: một lần sử dụng annotation cụ thể trên khai báo ấy.
- **`AnnotationValue`**: giá trị của một phần tử trong lần sử dụng annotation, ví dụ chuỗi `""` của `path`.

Nếu compiler/IDE hỗ trợ mapping vị trí nguồn, việc cung cấp đối tượng phù hợp cho `Messager` có thể giúp thông báo lỗi xuất hiện ngay gần khai báo, tên annotation hoặc biểu thức giá trị có vấn đề, thay vì thành một thông báo tổng quát khó tìm.

Đây là **diagnostic tại thời điểm biên dịch**, không phải exception được ném khi ứng dụng chạy. API này nằm trong module chuẩn `java.compiler`, thuộc Java SE 17+, không cần Spring, Lombok hoặc thư viện annotation ngoài.

## 2. Ba đối tượng định vị chẩn đoán

### 2.1. Element — khai báo cần chỉ ra

Trong `javax.lang.model.element`, `Element` mô tả một phần tử của chương trình ở mức mô hình biên dịch. Các loại phổ biến gồm:

| Phần tử source | Kiểu mô hình thường gặp | Ví dụ |
| --- | --- | --- |
| Class/interface | `TypeElement` | `class OrderService {}` |
| Phương thức hoặc constructor | `ExecutableElement` | `void save() {}` |
| Field hoặc parameter | `VariableElement` | `int timeout;`, tham số `int count` |
| Package | `PackageElement` | `package com.example;` |
| Module | `ModuleElement` | `module my.module {}` |

Từ một annotation processor, có thể lấy các phần tử được chú thích bằng:

```java
Set<? extends Element> elements =
        roundEnv.getElementsAnnotatedWith(Endpoint.class);
```

Đoạn minh họa nằm **trong `process`**, với `roundEnv` và `Endpoint` đã được định nghĩa. `Element` **không phải** `java.lang.reflect.Element`, và cũng không phải object của class `OrderService` khi chạy ứng dụng. Đây là mô hình chương trình do compiler cung cấp.

### 2.2. AnnotationMirror — lần sử dụng annotation

Một `Element` có thể chứa nhiều annotation:

```java
@Deprecated
@Endpoint(path = "/orders", retries = 2)
class OrderService {}
```

Nếu chỉ truyền `Element`, vị trí thông báo có thể gắn với cả khai báo `OrderService`. Muốn nhắm đến **lần sử dụng `@Endpoint(...)`**, lấy đúng `AnnotationMirror` từ `element.getAnnotationMirrors()` và truyền nó cùng `Element`.

`AnnotationMirror` biểu diễn một lần sử dụng annotation theo ngữ nghĩa compiler, gồm **annotation type** và các cặp phần tử/giá trị. Nó không phải đối tượng `Endpoint` được lấy bằng runtime reflection. Một class có thể mang nhiều annotation khác loại; vì vậy phải **chọn đúng mirror theo kiểu annotation**, không dùng luôn mirror đầu tiên trong danh sách.

### 2.3. AnnotationValue — giá trị phần tử annotation

Trong khai báo:

```java
@Endpoint(path = "/orders", retries = -1)
class OrderService {}
```

`path` và `retries` là **annotation elements**. Giá trị `-1` của `retries` được mô tả bằng một `AnnotationValue`. Khi có `Element`, `AnnotationMirror` và `AnnotationValue` tương ứng, có thể yêu cầu compiler định vị diagnostic gần giá trị đó.

Chú ý phân biệt ba thuật ngữ đều thường được dịch là “phần tử”:

- **Program element (`Element`)**: khai báo class `OrderService`.
- **Annotation element (`ExecutableElement`)**: accessor `retries()` được định nghĩa trong `@interface Endpoint`.
- **Annotation value (`AnnotationValue`)**: giá trị `-1` cấp cho `retries` trong một lần sử dụng cụ thể.

Cả `ExecutableElement` và `AnnotationValue` đều có vai trò khi duyệt `AnnotationMirror.getElementValues()`: khóa là **annotation element**, còn value là **giá trị**.

## 3. Bốn overload của Messager.printMessage

`javax.annotation.processing.Messager` định nghĩa bốn overload chính:

```java
void printMessage(Diagnostic.Kind kind, CharSequence msg);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a, AnnotationValue v);
```

Đây là **chữ ký API minh họa**, không phải đoạn code định nghĩa một interface mới. Sự khác nhau:

| Overload | Vị trí chẩn đoán được cung cấp | Dùng khi |
| --- | --- | --- |
| `(kind, msg)` | Không chỉ định phần tử source | Lỗi/tin nhắn toàn cục của processor |
| `(kind, msg, e)` | Một **khai báo `Element`** | Cả class/method/field sai hoặc không gắn lỗi được vào annotation cụ thể |
| `(kind, msg, e, a)` | Một **annotation `AnnotationMirror`** trên khai báo | Annotation sai như một tổng thể; không xác định được giá trị cụ thể |
| `(kind, msg, e, a, v)` | **Giá trị `AnnotationValue`** của annotation | Một argument rõ ràng của annotation có giá trị không hợp lệ |

**Quan trọng:** Ba tham số định vị phải là những đối tượng *có quan hệ thực sự*: `a` là annotation trên `e`, và `v` là giá trị trong `a`. Không nên lấy mirror của class A rồi gắn vào Element của class B.

`Messager` và kiểu enum `Diagnostic.Kind` đến từ hai package:

```java
import javax.annotation.processing.Messager;
import javax.tools.Diagnostic;
```

Thông thường không cần tự `new Messager()`. Trong `AbstractProcessor`, dùng:

```java
Messager messager = processingEnv.getMessager();
```

Đầu ra cụ thể (tên file, dòng, cột, mức highlight) do compiler/IDE quyết định. API **cung cấp ngữ cảnh định vị**, không cam kết mọi công cụ sẽ tô màu đúng một token hoặc in thông báo cùng một format.

## 4. Diagnostic.Kind: mức độ và ý nghĩa

Một số giá trị của `javax.tools.Diagnostic.Kind`:

| Kind | Ý nghĩa thông thường |
| --- | --- |
| `ERROR` | Báo lỗi khiến lần biên dịch không được coi là thành công |
| `WARNING` | Cảnh báo thông thường, không mặc định làm build thất bại |
| `MANDATORY_WARNING` | Cảnh báo bắt buộc được công cụ hiển thị theo quy tắc của nó |
| `NOTE` | Thông tin bổ sung, thường hữu ích khi kiểm tra processor |
| `OTHER` | Diagnostic không thuộc nhóm trên |

Một annotation processor có thể chọn:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "retries phải lớn hơn hoặc bằng 0",
        element, mirror, retriesValue);
```

Đây là đoạn mã minh họa khi `element`, `mirror` và `retriesValue` đã được lấy hợp lệ trong processor. Kết quả là **compiler diagnostic**, không phải `throw new IllegalArgumentException(...)`.

Đối với cấu hình thực sự không thể chấp nhận, dùng `ERROR` để ngăn dự án build thành công. Với thông tin mang tính hướng dẫn hoặc chính sách chưa bắt buộc, cân nhắc `WARNING` hoặc `NOTE`. Tùy chọn `-Werror` của `javac` có thể biến warning thành lỗi build; vì vậy không được suy diễn mọi warning luôn vô hại trong mọi pipeline.

## 5. Lấy đúng AnnotationMirror và AnnotationValue

### 5.1. Chọn mirror theo type, không theo vị trí mảng

Một phần tử có thể gắn nhiều annotation. Dựa vào `AnnotationMirror.getAnnotationType()` và `Types.isSameType` để chọn đúng:

```java
TypeElement endpointType =
        processingEnv.getElementUtils().getTypeElement("Endpoint");

for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    if (processingEnv.getTypeUtils().isSameType(
            mirror.getAnnotationType(), endpointType.asType())) {
        // Đây là lần sử dụng @Endpoint cần kiểm tra.
    }
}
```

Đây là mã nằm trong `process` có `element` và `processingEnv` phù hợp. Trong dự án có package, dùng **tên fully qualified** của annotation, ví dụ `com.example.annotations.Endpoint`; tên ngắn `Endpoint` chỉ dùng trong ví dụ không có package.

Không nên so sánh chuỗi `mirror.toString()` hoặc lấy phần tử thứ nhất của `getAnnotationMirrors()` để định vị annotation: chuỗi hiển thị và thứ tự xuất hiện không phải cơ chế chọn loại an toàn.

### 5.2. getElementValues() so với getElementValuesWithDefaults()

Một annotation có thể có phần tử mặc định:

```java
@interface Endpoint {
    String path() default "/default";
    int retries() default 0;
}
```

Khi sử dụng `@Endpoint`, hai giá trị hiệu lực vẫn tồn tại về mặt ngữ nghĩa, dù **không xuất hiện tường minh trong source**. Hai API cần phân biệt:

- `AnnotationMirror.getElementValues()`: trả ánh xạ các phần tử có giá trị **được cung cấp tường minh** trong lần sử dụng annotation. Những phần tử bị bỏ qua để nhận default không nằm trong ánh xạ này.
- `Elements.getElementValuesWithDefaults(mirror)`: trả ánh xạ các phần tử và giá trị hiệu lực **bao gồm default**, hữu ích khi validation phải xét mọi phần tử.

Ví dụ:

```java
@Endpoint(path = "/users")
class UserService {}
```

Với annotation trên, `getElementValues()` có `path`, nhưng không chứa `retries`; còn `getElementValuesWithDefaults()` có thể cho cả `path = "/users"` và `retries = 0`.

**Tại sao phải quan tâm điều này khi định vị lỗi?** Nếu một giá trị là **default** và người dùng không viết nó ở `@Endpoint`, thì không có biểu thức giá trị tương ứng trong khai báo đang xét để compiler trỏ vào. Nên gắn diagnostic ở **annotation `(e,a)`** hoặc ở **khai báo `(e)`**, thay vì giả định overload `(e,a,v)` luôn có một token nguồn chính xác để highlight.

### 5.3. Truy xuất tên phần tử và giá trị typed

`getElementValuesWithDefaults()` trả kiểu map:

```java
Map<? extends ExecutableElement, ? extends AnnotationValue> values =
        processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
```

Mỗi entry chứa:

- Khóa `ExecutableElement`, ví dụ phần tử `path()` hoặc `retries()`. Lấy tên bằng `entry.getKey().getSimpleName().toString()`.
- Giá trị `AnnotationValue`, có `getValue()` trả object theo loại phần tử: `String` cho `String`, `Integer` cho `int`, và các kiểu mô hình đặc thù khi giá trị là enum, class literal hoặc annotation lồng nhau.

Với code chỉ kiểm tra `String` và `int`, có thể cast phù hợp dựa trên định nghĩa annotation. Không được coi mọi `AnnotationValue.getValue()` đều là `String`. Với mảng annotation, giá trị trả về không phải array Java của annotation runtime; đối với annotation processor, API mô hình có những biểu diễn riêng (ví dụ danh sách `AnnotationValue`).

## 6. Ví dụ hoàn chỉnh Java 17+: gắn diagnostic vào 3 mức

Ví dụ gồm **bốn file Java** trong cùng một thư mục rỗng. Processor dùng `Messager.printMessage` ở ba mức:

1. **`Element`**: cảnh báo class `LegacyService` về quy ước đặt tên.
2. **`Element + AnnotationMirror`**: báo lỗi khi `@Endpoint` đặt trên một interface (dù `@Target(TYPE)` cho phép về cú pháp).
3. **`Element + AnnotationMirror + AnnotationValue`**: báo lỗi ngay giá trị `path` rỗng hoặc `retries` âm do lập trình viên cung cấp.

Trường hợp **giá trị mặc định** sẽ được xử lý với vị trí fallback hợp lý, không giả định luôn có argument trong source.

### 6.1. File Endpoint.java

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
@interface Endpoint {
    String path() default "/default";
    int retries() default 0;
}
```

`@Target(TYPE)` cho phép đặt `@Endpoint` trên class và interface, giúp processor kiểm tra một quy tắc **nghiệp vụ bổ sung**: trong ví dụ chỉ cho phép class. `@Retention(SOURCE)` đủ cho processor vì validation diễn ra khi biên dịch; chương trình runtime không cần reflection đọc `@Endpoint`.

### 6.2. File EndpointProcessor.java

```java
import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("Endpoint")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class EndpointProcessor extends AbstractProcessor {

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        TypeElement endpointType = processingEnv
                .getElementUtils().getTypeElement("Endpoint");
        if (endpointType == null) {
            return false;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(endpointType)) {
            for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
                boolean matches = processingEnv.getTypeUtils()
                        .isSameType(mirror.getAnnotationType(),
                                    endpointType.asType());
                if (!matches) {
                    continue;
                }

                if (element.getSimpleName()
                        .contentEquals("LegacyService")) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.WARNING,
                            "Nên đổi tên LegacyService",
                            element);
                }

                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "@Endpoint chỉ hỗ trợ class theo quy tắc dự án",
                            element, mirror);
                    continue;
                }

                Map<? extends ExecutableElement,
                    ? extends AnnotationValue> effectiveValues =
                        processingEnv.getElementUtils()
                                .getElementValuesWithDefaults(mirror);

                for (Map.Entry<? extends ExecutableElement,
                               ? extends AnnotationValue> entry
                        : effectiveValues.entrySet()) {
                    String name = entry.getKey()
                            .getSimpleName().toString();
                    Object raw = entry.getValue().getValue();

                    if (name.equals("path")
                            && ((String) raw).isBlank()) {
                        reportValueError(element, mirror,
                                entry.getKey(), entry.getValue(),
                                "path không được rỗng");
                    }

                    if (name.equals("retries")
                            && ((Integer) raw) < 0) {
                        reportValueError(element, mirror,
                                entry.getKey(), entry.getValue(),
                                "retries phải >= 0");
                    }
                }
            }
        }
        return true;
    }

    private void reportValueError(
            Element element, AnnotationMirror mirror,
            ExecutableElement key, AnnotationValue value,
            String message) {

        if (mirror.getElementValues().containsKey(key)) {
            // Giá trị được viết tường minh trong @Endpoint(...).
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, message,
                    element, mirror, value);
        } else {
            // Không có biểu thức nguồn cho giá trị mặc định.
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    message + " (từ giá trị mặc định)",
                    element, mirror);
        }
    }
}
```

**Giải thích:**

- `@SupportedAnnotationTypes("Endpoint")` khai báo annotation type do processor xử lý; vì ví dụ ở **default package**, tên `Endpoint` dùng được. Trong dự án thật có package, khai báo fully qualified name.
- `@SupportedSourceVersion(RELEASE_17)` cho biết processor hỗ trợ source Java 17.
- `processingOver()` giúp processor không cố xử lý phần tử mới ở vòng cuối.
- `getElementsAnnotatedWith(endpointType)` lấy các phần tử được chú thích `@Endpoint` trong vòng đang xét.
- `getAnnotationMirrors()` + `isSameType` giúp chọn đúng instance `@Endpoint` khi phần tử có nhiều annotation.
- `getElementValuesWithDefaults()` bảo đảm quy tắc validation cũng xem xét **giá trị mặc định**.
- `mirror.getElementValues().containsKey(key)` quyết định **có một biểu thức tường minh** để nhắm `AnnotationValue` hay không.
- `printMessage(ERROR, ..., element, mirror, value)` đặt diagnostic ở mức giá trị.
- `printMessage(ERROR, ..., element, mirror)` gắn diagnostic ở mức annotation khi không có giá trị tường minh hoặc khi chính nơi sử dụng annotation không phù hợp.
- `return true` có nghĩa claim annotation types, **không** có nghĩa không còn vòng xử lý.

### 6.3. File GoodDemo.java

```java
@Endpoint(path = "/orders", retries = 2)
class OrderService {}

@Endpoint
class DefaultService {}

@Endpoint(path = "/legacy")
class LegacyService {}
```

Đây là nguồn hợp lệ theo quy tắc của processor. Một `WARNING` có thể xuất hiện trên khai báo `LegacyService`, nhưng không có error diagnostic từ code trên.

### 6.4. File BadDemo.java

```java
@Endpoint(path = "", retries = -1)
class BrokenService {}

@Endpoint(path = "/interface")
interface InvalidContract {}
```

Chương trình này được **cố ý viết sai hợp đồng của processor**, dù cú pháp annotation/type tự thân hợp lệ. Processor báo:

- **Lỗi giá trị `path`** ở `""`.
- **Lỗi giá trị `retries`** ở `-1`.
- **Lỗi annotation** ở `@Endpoint(...)` trên interface `InvalidContract`, vì quy tắc dự án chỉ nhận class.

Số dòng/cột chính xác và cách gạch chân tùy compiler. Các lỗi này do processor báo qua `Messager`, không phải `RuntimeException` lúc chạy.

### 6.5. Lệnh javac kiểm thử

Với JDK 17+, tạo thư mục `build`, rồi từ thư mục chứa bốn file chạy:

```bash
mkdir -p build

javac --release 17 -d build Endpoint.java EndpointProcessor.java

javac --release 17 -cp build -processorpath build \
  -processor EndpointProcessor -d build GoodDemo.java

javac --release 17 -cp build -processorpath build \
  -processor EndpointProcessor -d build BadDemo.java
```

Lệnh **thứ nhất** biên dịch annotation type và processor. Lệnh **thứ hai** gọi processor trên nguồn hợp lệ và dự kiến kết thúc thành công, mặc dù có cảnh báo. Lệnh **thứ ba** cố ý phát sinh ERROR diagnostic nên dự kiến có mã thoát khác 0; đây là minh họa cách processor từ chối nguồn không hợp lệ.

Trong PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force build` và viết mỗi lệnh `javac` trên một dòng; ký tự `\` cuối dòng ở block `bash` là cú pháp shell kiểu Unix.

Thông điệp cốt lõi dự kiến thấy trong diagnostic:

```text
Nên đổi tên LegacyService
path không được rỗng
retries phải >= 0
@Endpoint chỉ hỗ trợ class theo quy tắc dự án
```

**Đây là các chuỗi thông điệp** do processor phát ra, **không phải stdout nguyên văn của compiler**. `javac` còn thêm mức `warning:`/`error:`, đường dẫn file, dòng/cột, đoạn source và số diagnostic; không nên kiểm thử bằng so sánh nguyên văn toàn bộ output compiler.

## 7. Khi nào chọn Element, AnnotationMirror hay AnnotationValue?

Sử dụng mức hẹp nhất **có ý nghĩa và có nguồn gốc hợp lệ**:

| Tình huống | Mức nên gắn | Lý do |
| --- | --- | --- |
| Tên class sai quy ước, không liên quan một annotation cụ thể | `Element` | Lỗi thuộc khai báo class |
| Một annotation không được phép trên loại khai báo này theo quy tắc thư viện | `Element + AnnotationMirror` | Cả lần sử dụng annotation là đối tượng cần sửa |
| `@Endpoint(retries = -1)` và `-1` được viết tường minh | `Element + AnnotationMirror + AnnotationValue` | Giá trị riêng của phần tử là nguyên nhân lỗi |
| Annotation dùng default không hợp lệ, nên không có biểu thức argument | `Element + AnnotationMirror` | Không có token giá trị ở nơi sử dụng để highlight |
| Sai cấu hình processor toàn cục, không quy về khai báo nào | `kind + message` | Diagnostic không có tọa độ phần tử cụ thể |

**Không cố ép diagnostic xuống mức giá trị** nếu thực chất lỗi là tổ hợp nhiều phần tử. Ví dụ `min = 100, max = 1` sai do quan hệ giữa hai giá trị; tùy UX có thể gắn lỗi vào annotation tổng thể hoặc vào một phần tử được xác định theo chính sách.

## 8. Ranh giới và bẫy khi gắn vị trí lỗi

### 8.1. Không bảo đảm IDE/compiler luôn highlight chính xác

Một số compiler tích hợp cung cấp source positions chính xác cho annotation values; công cụ khác có thể chỉ trỏ đến annotation hoặc declaration. `Messager` quy định vị trí **ngữ nghĩa** gắn với diagnostic, còn trình bày thông điệp/đường dẫn/dòng/cột là công việc của compiler và IDE.

Vì vậy, cần viết thông điệp tự đủ nghĩa ngay cả khi người dùng chỉ nhìn thấy:

```text
error: retries phải >= 0
```

Không nên phụ thuộc duy nhất vào mũi tên dưới một literal để giải thích lỗi.

### 8.2. Default value không nằm ở chỗ sử dụng

Với:

```java
@Endpoint
class DefaultService {}
```

`path` và `retries` lấy từ default của annotation type. Nếu ngày nào đó default bị định nghĩa sai theo quy tắc riêng, việc hỏi `getElementValuesWithDefaults()` vẫn thấy giá trị sai, nhưng source tại `@Endpoint` **không viết argument ấy**. Hãy gắn thông báo ở annotation/class và ghi rõ tên phần tử/default đang gây lỗi.

### 8.3. Mảng và annotation lồng nhau cần mô hình con

Ví dụ:

```java
@interface Rule {
    String name();
}

@interface Policy {
    Rule[] rules();
}
```

Khi `rules` là mảng annotation, `AnnotationValue.getValue()` ở mức phần tử có thể biểu diễn các giá trị con trong **mô hình javax.lang.model**. Không cast thành `Rule[]` runtime hoặc trông chờ giá trị `List<Rule>` của ứng dụng. Cần duyệt giá trị theo kiểu mô hình, chẳng hạn qua `AnnotationValueVisitor` hoặc kiểu `List<? extends AnnotationValue>`, và giữ đúng ngữ cảnh mirror/value khi phát diagnostic.

Nếu compiler API không cho chẩn đoán chi tiết đến nested child theo mong muốn, chọn vị trí annotation/mảng cha kèm thông điệp ghi rõ đường dẫn logic, ví dụ `rules[2].name`.

### 8.4. Phân biệt compiler model với runtime reflection

Trong annotation processor:

```java
element.getAnnotationMirrors()
```

lấy metadata của mô hình ngôn ngữ tại compile time, kể cả annotation không có `RUNTIME` retention ở source đang được xử lý.

Ở chương trình runtime:

```java
SomeClass.class.getAnnotation(Endpoint.class)
```

dùng reflection, phụ thuộc retention và API runtime. Hai biểu diễn khác nhau, không có lý do chuyển `AnnotationMirror` thành đối tượng `Endpoint` runtime để báo lỗi.

### 8.5. Không giữ Element qua lần biên dịch khác

`Element`, `AnnotationMirror` và `AnnotationValue` thuộc **processing environment** của phiên biên dịch. Nếu cần lưu danh sách lỗi lâu dài hoặc giữa các bản build, nên lưu thông tin logic thích hợp (tên type, tên phần tử, message code), không serialize thẳng object mô hình compiler.

Trong cùng một phiên, processor có thể trải nhiều vòng; khi lưu dữ liệu tích lũy, cần chú ý phần tử từ vòng trước có thể không còn phù hợp để xác định vị trí chính xác trong vòng sau. Tốt hơn nên báo lỗi ngay lúc thấy nguồn không hợp lệ ở vòng hiện tại.

### 8.6. Lỗi ngôn ngữ và lỗi nghiệp vụ khác nhau

Compiler kiểm tra cú pháp annotation, kiểu phần tử và `@Target`. Ví dụ `@Endpoint(retries = "three")` sẽ bị compiler từ chối vì `String` không khớp `int`. Processor phù hợp để kiểm tra **ràng buộc riêng**, như `retries >= 0` hoặc “annotation này chỉ hỗ trợ concrete class”.

Không nên cố sửa type error của compiler trong processor; một chương trình sai ngữ pháp có thể khiến mô hình nguồn không hoàn chỉnh hoặc processor không được gọi theo cách bạn mong đợi.

## 9. Quy trình chẩn đoán chuẩn cho annotation processor

1. **Khởi tạo:** lấy `processingEnv.getMessager()`, `getElementUtils()`, `getTypeUtils()`; khai báo các annotation được hỗ trợ.
2. **Chọn vòng:** nếu `roundEnv.processingOver()` thì không xử lý nguồn mới theo quy trình bình thường.
3. **Lấy phần tử:** dùng `getElementsAnnotatedWith(TypeElement)` để tìm mục tiêu của vòng.
4. **Chọn annotation:** so sánh `AnnotationMirror.getAnnotationType()` với đúng annotation type, không dựa vào vị trí mảng/chuỗi `toString`.
5. **Lấy giá trị:** đọc `getElementValues()` nếu quan tâm giá trị được viết tường minh; dùng `getElementValuesWithDefaults()` khi kiểm tra mọi giá trị hiệu lực.
6. **Kiểm tra invariant:** xác định lỗi thuộc toàn khai báo, annotation tổng thể hay một phần tử/giá trị cụ thể.
7. **Phát diagnostic:** dùng overload của `Messager.printMessage` có đủ ngữ cảnh nhưng không hơn khả năng định vị.
8. **Ngừng sinh mã sai:** nếu validation thất bại, tránh sinh output được coi là hợp lệ; `Diagnostic.Kind.ERROR` đảm bảo có chẩn đoán lỗi cho build.
9. **Kiểm thử:** dùng `javac -processor ...`, cả source tốt và source xấu; kiểm tra thông điệp, loại diagnostic và khi cần kiểm tra vị trí hiển thị trong compiler/IDE cụ thể.
10. **Giữ thông điệp rõ nghĩa:** ghi tên phần tử và kỳ vọng, ví dụ `retries phải >= 0`, không chỉ viết `Invalid value`.

## 10. Lỗi thường gặp và cách sửa

**1. Dùng printMessage(kind, msg) cho mọi lỗi.** Mất khả năng gắn lỗi vào source. Truyền `Element`, `AnnotationMirror`, `AnnotationValue` khi có vị trí hợp lệ.

**2. Lấy mirror đầu tiên để báo lỗi.** Một khai báo có nhiều annotation; phải tìm đúng loại annotation bằng type model.

**3. Dùng AnnotationMirror.toString() làm bộ chọn annotation.** Đây là dạng hiển thị, không phải phép so sánh type đáng tin. Dùng `Types.isSameType`.

**4. Bỏ qua giá trị mặc định.** `AnnotationMirror.getElementValues()` không chứa phần tử dùng default. Dùng `Elements.getElementValuesWithDefaults()` để validate đầy đủ.

**5. Luôn gắn lỗi vào AnnotationValue dù phần tử dùng default.** Không có token của giá trị đó tại lần sử dụng annotation. Fallback lên mức mirror hoặc declaration.

**6. Nhầm ExecutableElement và AnnotationValue.** Khóa map là khai báo accessor của phần tử; value mới là giá trị được cấp. Overload năm tham số cần `AnnotationValue`, không phải `ExecutableElement`.

**7. Cast mọi AnnotationValue.getValue() thành String.** Enum, class literal, nested annotation và array có biểu diễn mô hình khác. Dựa trên kiểu phần tử và visitor khi cần.

**8. Nghĩ Messager.ERROR ném Java exception ngay.** Diagnostic được công cụ biên dịch thu thập. Processor vẫn cần điều khiển luồng `process` và tránh sinh mã không hợp lệ.

**9. Nghĩ return true bảo đảm không có lỗi.** `true` chỉ claim annotation types; không có nghĩa compiler thành công.

**10. Dùng runtime reflection để tìm annotation SOURCE.** Annotation processor dùng API mô hình compile time, không dùng `Class.getAnnotation` để thay thế.

**11. Kiểm thử chính xác cả chuỗi đường dẫn, cột và caret từ javac.** Định dạng diagnostic có thể khác theo môi trường. Test nên ưu tiên loại ERROR/WARNING, nội dung message và vị trí tương đối khi công cụ hỗ trợ.

**12. Báo lỗi sau khi đã tạo file từ dữ liệu sai.** Xác thực trước khi gọi `Filer` để tránh artifact hỏng và các lỗi dây chuyền.

## 11. Bài tập thực hành

1. **Đổi vị trí cảnh báo:** Trong processor, đổi `printMessage(WARNING, ..., element)` thành `printMessage(WARNING, ..., element, mirror)`. So sánh vị trí IDE/`javac` chỉ tới `LegacyService` hay `@Endpoint`.
2. **Thêm ràng buộc:** Đổi `retries` mặc định thành `-1` trong `@interface Endpoint`. Kiểm tra `@Endpoint` không ghi `retries` vẫn bị processor báo lỗi; giải thích vì sao cần fallback về mirror.
3. **Đọc map tường minh:** In tên các khóa `ExecutableElement` từ `mirror.getElementValues()` và từ `getElementValuesWithDefaults()` trên `DefaultService`. Giải thích khác biệt.
4. **Annotation sai đối tượng:** Bỏ nhánh `ElementKind.CLASS` rồi thử `@Endpoint` trên interface. Thiết kế diagnostic rõ ràng vì sao quy tắc dự án không hỗ trợ interface.
5. **Nhiều annotation:** Thêm một annotation khác lên `BrokenService`. Giải thích vì sao không lấy `element.getAnnotationMirrors().get(0)`.
6. **Phần tử array:** Thêm `String[] roles() default {};` vào `Endpoint`. Với role trống, hãy chỉ ra cách duyệt array bằng mô hình `AnnotationValue` thay vì cố cast về runtime array.
7. **Tối ưu UX:** Với lỗi `path = ""` và `retries = -1`, đề xuất thông điệp nêu rõ cách sửa. Mở IDE để xem con trỏ diagnostic có trỏ tới đúng literal hay không.
8. **Tổ chức dự án:** Đặt `Endpoint` và processor trong package riêng, sửa `@SupportedAnnotationTypes` thành tên fully qualified, chạy lại hai lệnh `javac` thành công/thất bại.
9. **Kiểm thử trong build:** Dùng test compilation để kiểm tra số lượng diagnostic, severity và các message đã phát. Không yêu cầu so sánh caret từng ký tự giữa hai phiên bản JDK.

## 12. Tài liệu tham khảo Java SE 17

- [Messager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): bốn overload `printMessage` và cách liên kết diagnostic với vị trí nguồn.
- [AnnotationMirror — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): mô hình một lần sử dụng annotation và `getElementValues()`.
- [AnnotationValue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html): cách biểu diễn giá trị phần tử annotation.
- [Elements — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getElementValuesWithDefaults()` và các tiện ích mô hình.
- [RoundEnvironment — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): truy xuất `Element` theo annotation ở mỗi vòng.
- [Diagnostic.Kind — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): các mức diagnostic được compiler hỗ trợ.

**Tóm lại:** Trong annotation processor, hãy báo lỗi ở **mức hẹp nhất mà mô hình nguồn hỗ trợ**: `Element` cho khai báo, `Element + AnnotationMirror` cho annotation và `Element + AnnotationMirror + AnnotationValue` cho giá trị được cung cấp tường minh. Đọc default qua `getElementValuesWithDefaults()` nhưng không giả định default có vị trí argument trong source. Thông báo rõ ràng và định vị chính xác giúp người dùng sửa annotation nhanh và giảm lỗi trong build.
