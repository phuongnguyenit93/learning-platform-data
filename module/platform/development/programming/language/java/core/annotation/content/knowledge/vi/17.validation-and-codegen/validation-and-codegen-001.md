# Thiết kế quy tắc kiểm tra vị trí, kiểu và giá trị annotation trong Java

## 1. Bài toán: annotation hợp lệ về cú pháp chưa chắc hợp lệ về nghiệp vụ

Trong Java, annotation là metadata gắn lên những thành phần chương trình. Trình biên dịch `javac` đã biết các quy tắc ngôn ngữ, chẳng hạn:

- Annotation chỉ được gắn lên những vị trí do `@Target` cho phép.
- Phần tử annotation phải có kiểu hợp lệ: kiểu nguyên thủy, `String`, `Class`, enum, annotation khác hoặc mảng một chiều của các kiểu ấy.
- Các giá trị tại nơi gắn annotation phải đúng kiểu phần tử, là dạng giá trị được Java chấp nhận, và phần tử bắt buộc phải được cung cấp.
- Giá trị `default` trong định nghĩa annotation phải hợp lệ.

Tuy nhiên, quy tắc như **“annotation này chỉ được dùng trên phương thức trả về `String`, nhận đúng một tham số `String`, có `path` bắt đầu bằng dấu `/`, và `timeoutMs` từ 1 đến 5000”** là **quy tắc nghiệp vụ**. Java không tự suy chúng ra từ tên annotation. Muốn kiểm tra lúc biên dịch, ta xây **annotation processor** dùng API `javax.annotation.processing` và `javax.lang.model` để đọc mô hình khai báo, kiểm tra điều kiện, rồi xuất diagnostic.

Chủ đề này gồm ba trục kiểm tra:

1. **Vị trí (position):** annotation gắn ở khai báo gì? Class, method, field, parameter hay một vị trí type-use?
2. **Kiểu (type):** đối tượng mang annotation có chữ ký/kiểu phù hợp không? Phần tử annotation đã khai báo và giá trị được dùng có đúng kiểu không?
3. **Giá trị (value):** metadata có thỏa ràng buộc nội dung như chuỗi không rỗng, tiền tố `/`, miền số hoặc sự tương thích giữa các phần tử không?

Thiết kế tốt phải phân biệt **điều gì compiler kiểm tra sẵn** với **điều gì processor phải chủ động kiểm tra**.

## 2. Phân tầng quy tắc: ngôn ngữ, khai báo annotation và chính sách ứng dụng

| Tầng | Kiểm tra | Ai chịu trách nhiệm? | Ví dụ |
| --- | --- | --- | --- |
| Ngữ pháp và Java language rules | Loại annotation tồn tại, tên phần tử, kiểu phần tử, giá trị constant hợp lệ | `javac` | `@EndpointRule(path = 42)` sai vì `path()` là `String` |
| Vị trí theo `@Target` | Annotation được đặt ở `METHOD`, `TYPE`, `FIELD`...? | `javac` | `@Target(METHOD)` không cho phép gắn lên field |
| Nghĩa của khai báo gắn annotation | Method phải có đúng một tham số `String` và trả về `String` | Processor tùy chỉnh | Một method trả `int` bị từ chối bởi policy của thư viện |
| Giá trị metadata mang ý nghĩa riêng | `path` phải bắt đầu `/`; `timeoutMs` phải nằm trong miền cho phép | Processor tùy chỉnh | `path = "orders"` bị từ chối |
| Hành vi lúc chạy | Dùng `path` để đăng ký route và timeout để điều khiển xử lý | Runtime consumer/framework riêng | Processor không tự khởi chạy HTTP server |

**Nguyên tắc:** sử dụng `@Target` và kiểu phần tử để **loại bỏ càng nhiều lỗi nền tảng càng tốt ngay ở compiler**. Chỉ viết custom validator cho các điều kiện chưa được ngôn ngữ biểu đạt.

Bài ví dụ dưới đây cố ý cho `@EndpointRule` có hai đích `METHOD` và `TYPE` để trình diễn một **rule vị trí bổ sung bằng processor**: dù cú pháp Java cho phép gắn trên class, chính sách ứng dụng chỉ chấp nhận method. Trong thiết kế production thực sự chỉ muốn method, nên đổi thành `@Target(METHOD)` để compiler chặn sớm, giữ processor tập trung vào chữ ký và giá trị.

## 3. Thiết kế hợp đồng annotation

Giả sử hệ thống cần khai báo “endpoint” trên method:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.METHOD, ElementType.TYPE})
@interface EndpointRule {
    String path();
    int timeoutMs() default 1000;
}
```

Đây là **đoạn minh họa hợp đồng**, không phải file chương trình chạy độc lập. Ví dụ chạy đầy đủ ở mục 7 khai báo annotation này trong package `lesson`.

Chính sách mong muốn là:

- **EP001 — Vị trí:** chỉ gắn lên khai báo `METHOD`, dù `@Target` của ví dụ cố ý cho phép thêm `TYPE`.
- **EP002 — Kiểu trả về:** method phải trả `java.lang.String`.
- **EP003 — Kiểu và số lượng tham số:** phải có đúng một tham số với kiểu `java.lang.String`.
- **EP004 — Giá trị `path`:** phải bắt đầu bằng `/`, không rỗng và không có dấu cách.
- **EP005 — Giá trị `timeoutMs`:** phải nằm trong khoảng **1–5000**, kể cả hai đầu mút.

`timeoutMs() default 1000` cho phép nơi dùng bỏ qua timeout. Quy tắc EP005 vẫn phải kiểm tra **giá trị hiệu lực sau khi tính default**; không được mặc định rằng phần tử không xuất hiện trong source đồng nghĩa không có giá trị.

### Vì sao `SOURCE` đủ?

Processor chạy trong **quá trình biên dịch** và đọc các phần tử được compiler cung cấp. Nó không cần annotation tồn tại qua runtime Reflection. `@Retention(SOURCE)` là lựa chọn phù hợp nếu annotation chỉ phục vụ kiểm tra/generate code lúc build. Nếu framework runtime cũng muốn đọc `EndpointRule` bằng Reflection, khi đó phải đánh giá yêu cầu dùng `RUNTIME`.

## 4. Kiểm tra **vị trí** bằng `ElementKind`

Processor thường nhận các phần tử được gắn annotation thông qua:

```java
for (Element element :
        roundEnv.getElementsAnnotatedWith(EndpointRule.class)) {

    if (element.getKind() != ElementKind.METHOD) {
        // Báo diagnostic EP001 tại phần tử vi phạm.
        continue;
    }

    ExecutableElement method = (ExecutableElement) element;
    // Các kiểm tra dành riêng cho method.
}
```

Đây là **trích đoạn minh họa**; cần các import và class processor như mục 7.

- `Element` là giao diện nền của các khai báo trong mô hình ngôn ngữ.
- `getKind()` trả `ElementKind` như `CLASS`, `INTERFACE`, `METHOD`, `FIELD`, `PARAMETER`...
- Chỉ ép sang `ExecutableElement` **sau khi đã xác nhận** `ElementKind.METHOD`.
- Nếu rule dành cho parameter, hãy dùng `ElementKind.PARAMETER` và ép sang `VariableElement`; nếu dành cho class, dùng `TypeElement` sau khi kiểm tra kind tương ứng.

**Không nhầm `@Target` với custom position rule.** `@Target` là hợp đồng cú pháp mà compiler hiểu. Processor thêm điều kiện chặt hơn khi thật sự có nhu cầu. Một annotation gắn lên vị trí `FIELD` trong ví dụ này bị compiler từ chối bởi `@Target` ngay cả khi processor không xử lý nó.

Với annotation gắn trên **kiểu sử dụng** (`TYPE_USE`), việc tìm và phân tích cấu trúc có thể cần xử lý `TypeMirror` và cây AST (`com.sun.source.tree`) thay vì giả định mọi type-use annotation sẽ được trả trực tiếp từ `RoundEnvironment.getElementsAnnotatedWith(...)` dưới dạng một `Element` riêng. Bài này kiểm tra **annotation trên khai báo** và API Language Model tương ứng.

## 5. Kiểm tra **kiểu** bằng `TypeMirror` và `Types`

Một method có thể mang annotation đúng vị trí nhưng có chữ ký không phù hợp:

```java
// Trích đoạn sai về chính sách ứng dụng:
@EndpointRule(path = "/items")
int find(int id) {
    return id;
}
```

Đoạn này **có thể hợp lệ về cú pháp annotation** nhưng vi phạm cả EP002 và EP003.

Trong processor, phương thức có biểu diễn `ExecutableElement`; dùng:

- `method.getReturnType()`: nhận một `TypeMirror` của kiểu trả về.
- `method.getParameters()`: nhận danh sách `VariableElement` của các parameter.
- `parameter.asType()`: nhận `TypeMirror` của kiểu parameter.
- `processingEnv.getTypeUtils()`: nhận `Types` để so sánh kiểu.
- `processingEnv.getElementUtils().getTypeElement("java.lang.String").asType()`: tham chiếu mô hình kiểu `String`.

Trích đoạn:

```java
TypeMirror stringType = processingEnv.getElementUtils()
        .getTypeElement("java.lang.String").asType();

Types types = processingEnv.getTypeUtils();

boolean validReturn =
        types.isSameType(method.getReturnType(), stringType);

boolean validParameters =
        method.getParameters().size() == 1
        && types.isSameType(
                method.getParameters().get(0).asType(),
                stringType);
```

**Vì sao không so `toString()` của kiểu?** Trong thực tế có generic type, type variable, array, wildcard, annotation trên type use và những trường hợp compiler đang phục hồi lỗi. So sánh văn bản không phải phép kiểm tra ngữ nghĩa tổng quát. Dùng `Types.isSameType(...)` khi yêu cầu **đúng cùng kiểu**.

Nếu hợp đồng muốn chấp nhận subtype hoặc loại có thể gán cho nhau, có thể dùng `Types.isAssignable(...)` hoặc `Types.isSubtype(...)` theo hướng đúng. Ví dụ bài này cố ý yêu cầu **chính xác `String`** nên `isSameType` phù hợp.

## 6. Kiểm tra **giá trị** và giá trị mặc định bằng `AnnotationMirror`

Kiểu trả về của phần tử annotation đã được `javac` kiểm tra, nhưng **nghĩa của giá trị** như `path` và `timeoutMs` vẫn là quy tắc của thư viện.

Trong processor, một cách tổng quát là:

1. Lấy danh sách `element.getAnnotationMirrors()`.
2. Chọn đúng `AnnotationMirror` đại diện cho `@EndpointRule`.
3. Gọi `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` để nhận map các phần tử cùng giá trị, **kể cả default**.
4. Duyệt các entry `ExecutableElement` → `AnnotationValue`, xác định tên phần tử qua `getSimpleName()` và dữ liệu qua `AnnotationValue.getValue()`.
5. Kiểm tra chuỗi, số, quan hệ giữa các trường; phát diagnostic nếu không hợp lệ.

Ví dụ, nếu nơi dùng chỉ ghi:

```java
@EndpointRule(path = "/ping")
String ping(String name) { return "PONG:" + name; }
```

thì `AnnotationMirror.getElementValues()` phản ánh giá trị **ghi tường minh**, còn `Elements.getElementValuesWithDefaults(...)` giúp thấy thêm `timeoutMs = 1000`, vì `timeoutMs()` có `default 1000`.

Nếu tự dùng `mirror.getElementValues()` mà quên default, processor có thể bỏ sót ràng buộc hoặc xem nhầm phần tử là không có giá trị. Để kiểm tra hợp đồng **hiệu lực**, ưu tiên lấy map **with defaults**.

Trong ví dụ này:

| Phần tử | Kiểu Java khi gọi `AnnotationValue.getValue()` | Rule |
| --- | --- | --- |
| `path()` | `String` | Bắt đầu `/`, không rỗng và không có dấu cách |
| `timeoutMs()` | `Integer` | Từ 1 đến 5000 |

Với phần tử là `Class<?>`, annotation lồng nhau, enum hoặc mảng, `AnnotationValue.getValue()` có thể trả các cấu trúc ngôn ngữ như `TypeMirror`, `VariableElement`, `AnnotationMirror`, danh sách `AnnotationValue` chứ không phải trực tiếp các đối tượng runtime như `Class<?>`. Đó là lý do tool tổng quát thường cần `AnnotationValueVisitor` hoặc xử lý theo kiểu dữ liệu của mô hình compiler.

## 7. Chương trình Java 17+ hoàn chỉnh: annotation processor phát lỗi theo quy tắc

Đây là một ví dụ **compile-time**: processor kiểm tra class/method và báo lỗi ngay khi chạy `javac`. Ta tạo hai file Java để chạy trường hợp hợp lệ, và thêm file thứ ba khi muốn kiểm tra lỗi.

Cấu trúc thư mục:

```text
project/
└── lesson/
    ├── EndpointRuleProcessor.java
    ├── ServiceEndpoints.java
    └── InvalidEndpoints.java   (chỉ tạo khi thử trường hợp sai)
```

### File 1: `lesson/EndpointRuleProcessor.java`

```java
package lesson;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
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
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.METHOD, ElementType.TYPE})
@interface EndpointRule {
    String path();
    int timeoutMs() default 1000;
}

@SupportedAnnotationTypes("lesson.EndpointRule")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class EndpointRuleProcessor extends AbstractProcessor {

    private void error(String code, String message, Element element) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                code + ": " + message,
                element);
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        Elements elements = processingEnv.getElementUtils();
        Types types = processingEnv.getTypeUtils();
        TypeMirror stringType =
                elements.getTypeElement("java.lang.String").asType();
        TypeMirror annotationType =
                elements.getTypeElement("lesson.EndpointRule").asType();

        for (Element element :
                roundEnv.getElementsAnnotatedWith(EndpointRule.class)) {

            if (element.getKind() != ElementKind.METHOD) {
                error("EP001", "EndpointRule chi duoc gan tren method",
                        element);
                continue;
            }

            ExecutableElement method = (ExecutableElement) element;

            if (!types.isSameType(method.getReturnType(), stringType)) {
                error("EP002", "Method phai tra ve String", method);
            }

            boolean validParameters =
                    method.getParameters().size() == 1;
            if (validParameters) {
                VariableElement parameter = method.getParameters().get(0);
                validParameters =
                        types.isSameType(parameter.asType(), stringType);
            }
            if (!validParameters) {
                error("EP003", "Can dung mot tham so String", method);
            }

            for (AnnotationMirror mirror :
                    element.getAnnotationMirrors()) {

                if (!types.isSameType(
                        mirror.getAnnotationType(), annotationType)) {
                    continue;
                }

                String path = null;
                Integer timeoutMs = null;

                Map<? extends ExecutableElement, ? extends AnnotationValue>
                        values = elements.getElementValuesWithDefaults(mirror);

                for (Map.Entry<? extends ExecutableElement,
                        ? extends AnnotationValue> entry : values.entrySet()) {
                    String name =
                            entry.getKey().getSimpleName().toString();
                    Object value = entry.getValue().getValue();

                    if ("path".equals(name)) {
                        path = (String) value;
                    } else if ("timeoutMs".equals(name)) {
                        timeoutMs = (Integer) value;
                    }
                }

                if (path == null || !path.startsWith("/")
                        || path.contains(" ")) {
                    error("EP004",
                            "path phai bat dau bang / va khong co dau cach",
                            element);
                }

                if (timeoutMs == null
                        || timeoutMs < 1 || timeoutMs > 5000) {
                    error("EP005",
                            "timeoutMs phai trong khoang 1..5000",
                            element);
                }
            }
        }

        return true;
    }
}
```

**Giải thích các quyết định quan trọng:**

- `@SupportedAnnotationTypes("lesson.EndpointRule")` công bố annotation được xử lý.
- `@SupportedSourceVersion(RELEASE_17)` khai báo phiên bản nguồn được hỗ trợ.
- `RoundEnvironment.getElementsAnnotatedWith(EndpointRule.class)` lấy các khai báo đang được gắn annotation trong round phù hợp.
- `ElementKind.METHOD` là rào chắn trước khi ép thành `ExecutableElement`.
- `Types.isSameType` so sánh chính xác kiểu trả về và kiểu tham số.
- `getElementValuesWithDefaults` bảo đảm đọc cả `timeoutMs` mặc định.
- `Diagnostic.Kind.ERROR` khiến compiler báo lỗi và quá trình biên dịch thất bại nếu có vi phạm.
- `roundEnv.processingOver()` giúp bỏ qua công việc khi vòng xử lý kết thúc.

Thông báo EP001...EP005 dùng nội dung ASCII trong mã nguồn để kết quả ổn định trên nhiều terminal; văn bản hướng dẫn vẫn giải thích bằng tiếng Việt. Một processor sản xuất có thể dùng mã thông báo và nội dung đã quốc tế hóa tùy yêu cầu.

### File 2: `lesson/ServiceEndpoints.java` — trường hợp hợp lệ

```java
package lesson;

public class ServiceEndpoints {
    @EndpointRule(path = "/items", timeoutMs = 2500)
    public String find(String id) {
        return "ITEM:" + id;
    }

    @EndpointRule(path = "/ping")
    public String ping(String name) {
        return "PONG:" + name;
    }

    public static void main(String[] args) {
        ServiceEndpoints service = new ServiceEndpoints();
        System.out.println(service.find("A1"));
        System.out.println(service.ping("Lan"));
    }
}
```

Các phương thức `find` và `ping` đều thỏa quy tắc: gắn trên `METHOD`, trả `String`, nhận đúng một `String`, path bắt đầu `/`. `find` cung cấp timeout `2500`, còn `ping` nhận default `1000`; cả hai thuộc miền cho phép.

### Biên dịch hai bước

Từ thư mục `project`, chạy với JDK 17 trở lên:

```bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out lesson/EndpointRuleProcessor.java
javac --release 17 -encoding UTF-8 -cp out -processorpath out -processor lesson.EndpointRuleProcessor -d out lesson/ServiceEndpoints.java
java -cp out lesson.ServiceEndpoints
```

Lệnh `mkdir -p` áp dụng cho shell kiểu Bash. Nếu dùng Windows PowerShell, có thể tạo thư mục bằng `New-Item -ItemType Directory -Force out`; các lệnh `javac` và `java` phía sau giữ nguyên.

**Stdout của lệnh `java` cuối cùng:**

```text
ITEM:A1
PONG:Lan
```

Khi biên dịch file hợp lệ, processor không phát lỗi `ERROR` nên `javac` kết thúc thành công và thông thường không in dòng diagnostic nào liên quan EP001...EP005.

Cần phân biệt: processor **không thực hiện HTTP routing**. Ví dụ `main` chỉ gọi hai method Java bình thường. Annotation là hợp đồng biên dịch để kiểm tra chữ ký và metadata; muốn có server thực tế cần một consumer runtime hoặc đoạn mã sinh registry khác.

## 8. Thử trường hợp sai và đọc diagnostic

### File 3: `lesson/InvalidEndpoints.java`

File này **cố ý vi phạm quy tắc của processor**, không được trộn vào bước biên dịch trường hợp hợp lệ:

```java
package lesson;

@EndpointRule(path = "/class")
class InvalidClass {}

class InvalidEndpoints {
    @EndpointRule(path = "orders", timeoutMs = 0)
    int broken(int id) {
        return id;
    }
}
```

Với file này, `javac` vẫn chấp nhận **vị trí gắn annotation trên class** về mặt `@Target` vì khai báo demo có `TYPE`, nhưng processor phát EP001. Tương tự, method `broken` có chữ ký và metadata phù hợp với cú pháp Java, song vi phạm các quy tắc nghiệp vụ.

Biên dịch riêng file sai, sau khi đã có processor trong `out`:

```bash
javac --release 17 -encoding UTF-8 -cp out -processorpath out -processor lesson.EndpointRuleProcessor -d out lesson/InvalidEndpoints.java
```

Lệnh này **phải thất bại**. Tùy JDK và cách trình bày diagnostic, thứ tự/định dạng dòng có thể thay đổi; các **mã lỗi mong đợi** là:

| Mã | Nơi sai | Nguyên nhân |
| --- | --- | --- |
| `EP001` | `InvalidClass` | Policy chỉ chấp nhận `METHOD` dù `@Target` demo có thêm `TYPE` |
| `EP002` | `broken` | Trả về `int`, không phải `String` |
| `EP003` | `broken` | Parameter `int id`, không phải đúng một `String` |
| `EP004` | `broken` | `path = "orders"` không bắt đầu bằng `/` |
| `EP005` | `broken` | `timeoutMs = 0` nằm ngoài đoạn 1–5000 |

Thông báo có thể có tên tệp, số dòng, ký hiệu `error:`, vị trí con trỏ và tổng số lỗi phụ thuộc compiler. **Không coi toàn bộ stderr là một chuỗi cố định**. Điều cần kiểm chứng là các mã EP001...EP005 xuất hiện và không có file class hợp lệ được coi là sản phẩm build thành công.

Nếu đổi `@EndpointRule(path = "orders")` thành `@EndpointRule(path = 7)`, đây lại là **lỗi kiểu phần tử mà javac tự phát hiện** (`path()` là `String`), không phải một tình huống processor phải tự phát minh EP004.

Nếu gắn `@EndpointRule` vào một field trong demo, `javac` từ chối do `@Target` không chứa `FIELD`. Những lỗi này minh họa ranh giới giữa Java language rules và custom processor.

## 9. Thiết kế processor đáng tin: checklist

### 9.1 Định nghĩa rule bằng điều kiện có thể kiểm thử

Mỗi rule nên có:

- **ID ổn định:** EP001, EP002,... để IDE, CI và test dễ nhận diện.
- **Phạm vi:** loại `ElementKind`, loại annotation, package/module cần áp dụng.
- **Điều kiện hợp lệ:** biểu thức logic rõ ràng, ví dụ `1 <= timeoutMs <= 5000`.
- **Mức độ:** `ERROR` khi phải chặn build, `WARNING` nếu chỉ cảnh báo.
- **Diagnostic hữu ích:** nói **điều gì sai** và **giá trị hợp lệ** là gì.
- **Bộ test:** một hoặc nhiều ví dụ pass và fail tại đúng ranh giới.

Đừng dùng exception không kiểm soát để báo lỗi hợp đồng của người dùng. `processingEnv.getMessager().printMessage(ERROR, ..., element)` giúp compiler gắn lỗi vào thành phần có vấn đề. Với giá trị annotation cụ thể, overload của `Messager.printMessage` còn có thể gắn diagnostic với `AnnotationMirror` và `AnnotationValue` để chỉ đúng vị trí.

### 9.2 Thiết kế policy cho kiểu có chủ đích

Ví dụ trên yêu cầu **chính xác `String`**, không chấp nhận `CharSequence`. Nếu thư viện muốn cho phép subtype/kiểu có thể gán, cần đổi logic `Types` phù hợp và thêm test minh bạch. Đừng vô tình nới rộng hợp đồng chỉ vì so sánh văn bản hoặc tự động boxing.

Các kiểu generic, varargs, constructor, static method, method abstract hoặc overload cần quy định riêng nếu nghiệp vụ yêu cầu. `getKind()` và `Types` chỉ là công cụ kiểm tra, không tự quyết định các hạn chế ấy.

### 9.3 Không bỏ sót default hoặc annotation lồng nhau

Nếu rule liên quan tới `timeoutMs`, hãy kiểm tra **giá trị hiệu lực** kể cả khi người dùng bỏ qua phần tử. Với kiểu enum, class literal, annotation lồng nhau hoặc mảng, cần xử lý đúng đối tượng của `javax.lang.model`, không giả định mọi giá trị là `String` hoặc `Integer`.

Với annotation lặp (`@Repeatable`), có thể cần xử lý container và quy tắc áp dụng nhiều marker tùy API/compiler. Không nên suy từ một ví dụ đơn lẻ rằng `getElementsAnnotatedWith` tự xử lý mọi kiểu nesting theo ý nghiệp vụ.

### 9.4 Tách validator, rule và hành vi sinh mã

Bài toán “kiểm tra và sinh mã” thường có hai vai trò:

1. **Validator:** đọc `Element`/`TypeMirror`/`AnnotationMirror`, phát `ERROR` hoặc `WARNING`.
2. **Generator:** từ các khai báo hợp lệ, dùng `Filer` để sinh source/resource đúng một lần và xử lý nhiều vòng biên dịch.

Không nên sinh mã dựa trên dữ liệu **đã biết sai**. Nếu cần registry generated từ endpoint, hãy xây phần sinh mã sau bước xác thực, định nghĩa cách xử lý trùng `path`, tên lớp sinh ra, thứ tự ổn định và tránh lỗi `FilerException` do cố tạo cùng tệp ở nhiều round.

Ví dụ này cố ý **chỉ kiểm tra**, không sinh registry, để nội dung tập trung vào thiết kế ba loại rule. Điều đó cũng tránh ngộ nhận annotation tự tạo HTTP endpoint.

### 9.5 Kiểm soát nhiều round và lỗi mô hình

Annotation processing có thể có nhiều vòng, nhất là khi các processor khác sinh source mới. Không được giả định `process` chỉ gọi một lần. Khi `roundEnv.processingOver()` là `true`, không tạo source mới; dùng điều kiện phù hợp để bỏ qua phần đã xử lý. Với các khai báo có `TypeKind.ERROR` do phụ thuộc thiếu, processor sản xuất cần chọn tiếp tục, trì hoãn hoặc báo lỗi rõ ràng thay vì ép kiểu gây exception.

Bên cạnh đó, processor không nên quét/tải tùy tiện lớp runtime qua `Class.forName` để kiểm tra source đang biên dịch. Mô hình `javax.lang.model` là nguồn dữ liệu chính xác hơn cho bước compile-time.

## 10. Bảng test gợi ý cho từng rule

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| `@EndpointRule(path = "/ok") String run(String x)` | Hợp lệ; timeout dùng default 1000 |
| `@EndpointRule(path = "/ok", timeoutMs = 1)` trên method hợp lệ | Hợp lệ tại biên dưới |
| `@EndpointRule(path = "/ok", timeoutMs = 5000)` trên method hợp lệ | Hợp lệ tại biên trên |
| Annotation trên class (trong demo `@Target` có `TYPE`) | EP001 |
| Method trả `int` | EP002 |
| Method không có tham số hoặc hai tham số | EP003 |
| Method nhận `Integer` thay vì `String` | EP003 |
| `path = ""`, `path = "items"` hoặc `path = "/has space"` | EP004 |
| `timeoutMs = 0` hoặc `5001` | EP005 |
| `path = 123` | Lỗi kiểu từ compiler, trước/ngoài custom rule |
| Annotation trên field trong demo | Lỗi `@Target` của compiler |

Một bộ kiểm thử processor hoàn chỉnh cũng nên bao gồm các tổ hợp lỗi, chỗ gắn annotation lặp, nhiều module và trường hợp dependency thiếu khi đó là phạm vi hỗ trợ của thư viện. Test output nên so **mã diagnostic/ý nghĩa**, không bắt buộc so toàn bộ stderr vì vị trí dòng và định dạng JDK có thể thay đổi.

## 11. Những lỗi thiết kế phổ biến

**Lỗi 1 — Dùng processor để tái kiểm tra mọi thứ `javac` đã kiểm tra.** Nếu chỉ muốn hạn chế lên method, nên khai báo `@Target(METHOD)`; không nên buộc người học hiểu sai rằng chính sách loại vị trí hoàn toàn thuộc processor.

**Lỗi 2 — Ép `Element` sang `ExecutableElement` trước khi xét kind.** Một annotation có thể được gắn trên class hoặc biến, khiến ép kiểu sai. Cần xét `ElementKind` trước.

**Lỗi 3 — So kiểu bằng chuỗi `asType().toString()`.** Không tổng quát cho generic, subtype, nested types. Dùng `Types` với phép so sánh hợp đồng yêu cầu.

**Lỗi 4 — Chỉ đọc giá trị tường minh của `AnnotationMirror`.** Bỏ qua `default` có thể khiến rule được đánh giá sai. Dùng `getElementValuesWithDefaults` khi policy cần giá trị thực tế.

**Lỗi 5 — Nghĩ `@Retention(RUNTIME)` là điều kiện để processor nhìn thấy annotation.** Processor chạy khi biên dịch, `SOURCE` là đủ cho quy tắc compile-time.

**Lỗi 6 — Nhầm lỗi compiler với lỗi policy.** `path = 123` sai về kiểu Java, còn `path = "items"` sai về nội dung business. Hai lỗi nên được giải thích khác nhau.

**Lỗi 7 — Đưa dữ liệu chưa xác thực vào mã sinh.** Registry được generate có thể nhận path không hợp lệ, duplicate hoặc chữ ký phương thức không hỗ trợ.

**Lỗi 8 — Dùng `System.out.println` làm kênh báo lỗi chính.** Build/IDE có thể không phân loại hay gắn vị trí chính xác. Dùng `Messager` và `Diagnostic.Kind.ERROR` hoặc `WARNING`.

**Lỗi 9 — Không kiểm tra biên miền giá trị.** Đoạn `1..5000` phải kiểm tra cả 1 và 5000 là hợp lệ, 0 và 5001 là lỗi.

**Lỗi 10 — Cố suy hành vi runtime từ compile-time validation.** Khi processor chấp nhận `@EndpointRule(path = "/ok")`, JVM chưa có bộ định tuyến. Consumer sinh mã/registry hoặc runtime framework phải được thiết kế riêng nếu muốn endpoint thực sự hoạt động.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `@Target(METHOD)` có đủ để đảm bảo method nhận đúng một `String` và trả `String` không?

**Đáp án:** Không. `@Target` chỉ kiểm tra loại vị trí gắn; chữ ký method cần processor hoặc một cơ chế khác kiểm tra.

**Câu 2.** Trong ví dụ có `@Target({METHOD, TYPE})`, tại sao `@EndpointRule` trên class gây EP001 mà không phải lỗi cú pháp annotation của `javac`?

**Đáp án:** `TYPE` có trong `@Target` nên compiler cho phép vị trí class. EP001 là **quy tắc chặt hơn của processor**.

**Câu 3.** Muốn kiểm tra kiểu trả về method trong processor, nên dùng API nào?

**Đáp án:** `ExecutableElement.getReturnType()` trả `TypeMirror`, rồi `Types.isSameType` hoặc phép so sánh kiểu tương ứng với hợp đồng.

**Câu 4.** Vì sao `@EndpointRule(path="/ping")` vẫn có giá trị timeout để kiểm tra?

**Đáp án:** `timeoutMs()` có `default 1000`; `Elements.getElementValuesWithDefaults(mirror)` trả các giá trị sau khi tính cả default.

**Câu 5.** `path = 7` và `path = "ping"` sai giống nhau không?

**Đáp án:** Không. `7` là sai kiểu so với phần tử `String path()` nên compiler xử lý; `"ping"` đúng kiểu nhưng vi phạm EP004 của policy.

**Câu 6.** Processor báo lỗi EP005 bằng `Diagnostic.Kind.ERROR` thì `javac` được kỳ vọng làm gì?

**Đáp án:** Báo diagnostic tại phần tử tương ứng và kết thúc biên dịch với trạng thái lỗi; không coi build là thành công.

**Câu 7.** Với annotation chứa một phần tử kiểu `Class<?>`, kết quả `AnnotationValue.getValue()` trong processor có phải luôn là `java.lang.Class<?>` runtime không?

**Đáp án:** Không. Mô hình compile-time biểu diễn class literal bằng dữ liệu kiểu như `TypeMirror`, tránh yêu cầu load một class đang biên dịch.

**Câu 8.** Sau khi processor kiểm tra thành công, annotation tự sinh mã endpoint hay khởi chạy web server không?

**Đáp án:** Không. Validator chỉ kiểm tra. Sinh mã cần logic `Filer`; thực thi HTTP cần consumer phù hợp.

**Câu 9.** Tại sao nên có mã diagnostic ổn định EP001...EP005?

**Đáp án:** Để test, CI và IDE dễ nhận diện lỗi ngay cả khi ngôn ngữ thông báo hoặc số dòng source thay đổi.

**Câu 10.** Muốn thay quy tắc “chính xác `String`” thành “có thể gán cho `CharSequence`”, nên chỉ sửa phép so chuỗi không?

**Đáp án:** Không. Cần xác định chiều gán, dùng `Types.isAssignable(...)` hoặc API kiểu thích hợp và bổ sung bộ test về subtype/generic.

**Ghi nhớ:** Hãy dùng `@Target` và khai báo kiểu phần tử để `javac` bảo vệ các ràng buộc ngôn ngữ; dùng `ElementKind` để kiểm tra vị trí khai báo, `TypeMirror`/`Types` để kiểm tra chữ ký, `AnnotationMirror`/`AnnotationValue` cùng `getElementValuesWithDefaults` để kiểm tra nội dung metadata; báo lỗi bằng `Messager` và tách logic sinh mã/runtime khỏi validation.
