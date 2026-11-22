# Thực hành: tạo annotation mô tả thông tin tài liệu bằng enum, Class và giá trị mặc định

Bài thực hành này xây dựng một annotation Java tên `@DocInfo` để mô tả **metadata của tài liệu hoặc API**, gồm tiêu đề, trạng thái xuất bản, loại trình bày, kiểu liên quan, số phiên bản và các thẻ từ khóa. Thay vì nhét mọi thông tin vào một chuỗi khó kiểm tra, ta sử dụng đúng những **kiểu element hợp lệ** của annotation Java: `String`, `enum`, `Class<?>`, `Class<? extends Renderer>`, `int` và `String[]`. Một số element sẽ có giá trị `default`, để người dùng chỉ cần chỉ rõ những gì khác mặc định.

Kết quả mong muốn:

```java
@DocInfo(title = "Quick start")
class QuickStart {}
```

Với một khai báo ngắn, người đọc metadata vẫn lấy được `state = DRAFT`, `renderer = PlainRenderer.class`, `related = Void.class`, `revision = 1` và mảng `tags = {}`. Những giá trị này không phải do `QuickStart` khai báo thêm, mà do **định nghĩa annotation cung cấp mặc định**.

Nếu class khác cần ghi thông tin đầy đủ:

```java
@DocInfo(
    title = "API guide",
    state = DocState.PUBLISHED,
    renderer = HtmlRenderer.class,
    related = String.class,
    revision = 2,
    tags = {"java", "api"}
)
class ApiGuide {}
```

**Quan trọng:** annotation chỉ mang dữ liệu mô tả; nó không tự xuất bản tài liệu, không tự gọi renderer và không tự kiểm tra tiêu đề hợp lệ. Hành vi nghiệp vụ phải nằm trong code sử dụng annotation: reflection, annotation processor hoặc một framework được thiết kế để đọc nó.

## 1. Yêu cầu của mô hình tài liệu

Ta muốn biểu diễn những thuộc tính sau:

| Element | Kiểu Java | Bắt buộc khi gắn annotation? | Ý nghĩa |
|---|---|---|---|
| `title()` | `String` | Có, vì không có `default` | Tên tài liệu |
| `state()` | `DocState` | Không | Trạng thái `DRAFT`, `REVIEW`, `PUBLISHED` |
| `renderer()` | `Class<? extends Renderer>` | Không | Class triển khai `Renderer` được chọn |
| `related()` | `Class<?>` | Không | Một class được tài liệu nói đến |
| `revision()` | `int` | Không | Số phiên bản logic |
| `tags()` | `String[]` | Không | Nhiều từ khóa, theo thứ tự khai báo |

Ví dụ cần chọn giữa trạng thái `DRAFT` và `PUBLISHED`? Dùng **enum**, không phải chuỗi tự do, để compiler nhận biết các hằng hợp lệ. Ví dụ cần chỉ định class thực hiện rendering? Dùng **class token** `HtmlRenderer.class`, chứ không ghi tên class dưới dạng chuỗi `"HtmlRenderer"` rồi tự parse.

Những điều mà Java có thể kiểm tra ngay khi biên dịch:

- Giá trị `state` phải là một hằng của **đúng enum `DocState`**.
- Giá trị `renderer` phải là **class token tương thích `Class<? extends Renderer>`**.
- `related` nhận class token như `String.class`, `Integer.class` hoặc `Void.class`.
- `tags` chỉ chứa `String`, không thể viết giá trị số nguyên trong mảng `String[]`.
- Nếu bỏ `title`, compiler báo thiếu element bắt buộc; nếu bỏ `revision`, compiler dùng `default 1`.

Những điều Java **không tự kiểm tra theo nhu cầu nghiệp vụ**:

- `title` không được rỗng hoặc toàn dấu cách.
- `revision` phải là số dương.
- `PUBLISHED` phải có một bộ thẻ tối thiểu.
- Renderer có public no-arg constructor và thực sự render đúng.
- `related` phải trỏ tới một lớp thuộc domain mà dự án chấp nhận.

Đó là khác biệt giữa **hợp lệ theo kiểu của annotation** và **hợp lệ theo hợp đồng ứng dụng**.

## 2. Kiểu element nào được phép trong annotation interface?

Theo Java Language Specification §9.6.1, kiểu trả về của annotation element phải thuộc một trong những nhóm được Java cho phép:

1. Một kiểu primitive như `int`, `long`, `boolean`, `double`.
2. `String`.
3. `Class` hoặc một dạng sử dụng `Class` với type argument hợp lệ.
4. Một enum type.
5. Một annotation interface type.
6. Một mảng **một chiều** có component type thuộc các nhóm trên.

Ví dụ hợp lệ:

```java
@interface SampleMetadata {
    String title();
    int version() default 1;
    boolean archived() default false;
    Class<?> related() default Void.class;
    String[] keywords() default {};
}
```

Một số khai báo không hợp lệ:

```java
// Không hợp lệ theo quy tắc annotation element:
// @interface Invalid {
//     java.util.List<String> tags();        // List không được chấp nhận
//     java.util.Map<String, String> data(); // Map không được chấp nhận
//     String[][] matrix();                  // Mảng nhiều chiều không hợp lệ
//     Object value();                       // Object không phải element type hợp lệ
// }
```

Annotation interface không thể tự do trở thành một generic interface mang type parameter như `@interface DocInfo<T>`. Nếu cần giới hạn kiểu class, hãy dùng **bounded class token element**: `Class<? extends Renderer>`, với `Renderer` là một kiểu Java cụ thể, không phải type parameter của annotation.

Không thể dùng `null` làm annotation element value, kể cả khi element có kiểu tham chiếu như `String`, `Class` hoặc annotation con. Vì vậy có thể dùng một giá trị sentinel được định nghĩa rõ, ví dụ `Void.class`, cho ý nghĩa “không có class liên quan”.

## 3. Dùng enum để khóa danh sách trạng thái hợp lệ

Ta khai báo:

```java
enum DocState {
    DRAFT,
    REVIEW,
    PUBLISHED
}
```

Sau đó annotation:

```java
@interface DocInfo {
    DocState state() default DocState.DRAFT;
}
```

Ở nơi sử dụng:

```java
@DocInfo(state = DocState.PUBLISHED)
class FinalGuide {}
```

Compiler đảm bảo `state` nhận một enum constant tương thích. Nếu gõ `DocState.PUBLISH` không tồn tại, lỗi được phát hiện khi biên dịch; nếu gõ chuỗi `"PUBLISHED"`, kiểu không phù hợp nên cũng lỗi.

**Không nhầm điều này với tự động kiểm tra workflow.** Enum không khiến tài liệu tự chuyển `DRAFT -> REVIEW -> PUBLISHED`, không bảo đảm tài liệu có reviewer hoặc đã được upload. Enum chỉ làm cho tập trạng thái có tên và kiểu rõ ràng.

Khi nào dùng enum?

- Có một tập hữu hạn, có thể đặt tên rõ ràng.
- Muốn các nhánh `switch` trên trạng thái dễ đọc.
- Muốn compiler ngăn typo ở annotation value.
- Muốn reflection trả thẳng `DocState` thay vì một chuỗi cần parse.

Nếu trạng thái có xu hướng do quản trị viên thêm mới lúc runtime mà không build lại code, một enum cố định có thể không phù hợp. Nhưng với hợp đồng annotation compile-time như bài này, enum là lựa chọn tự nhiên.

## 4. Class<?> và Class<? extends Renderer> khác nhau ra sao?

`Class<?>` có thể chứa class token của nhiều loại:

```java
String.class
Integer.class
Void.class
int.class
String[].class
```

Vì type argument là wildcard không giới hạn, nó không buộc class được chọn thuộc một hierarchy riêng.

`Class<? extends Renderer>` hạn chế giá trị được chọn tới kiểu `Renderer` hoặc lớp con/implementation tương thích. Ví dụ:

```java
interface Renderer {
    String render(String title);
}

class PlainRenderer implements Renderer {
    public String render(String title) {
        return "PLAIN: " + title;
    }
}

class HtmlRenderer implements Renderer {
    public String render(String title) {
        return "<h1>" + title + "</h1>";
    }
}
```

Khi element được khai báo:

```java
@interface DocInfo {
    Class<? extends Renderer> renderer() default PlainRenderer.class;
}
```

thì hai ví dụ sau hợp lệ:

```java
@DocInfo(renderer = HtmlRenderer.class)
class HtmlDocument {}

@DocInfo(renderer = PlainRenderer.class)
class PlainDocument {}
```

Ví dụ này **không hợp lệ**, vì `String` không triển khai `Renderer`:

```java
// @DocInfo(renderer = String.class)
// class InvalidRenderer {}
```

Đây là một lợi thế lớn so với chuỗi `renderer = "com.example.HtmlRenderer"`: compiler phát hiện được class token không khớp bound khi tác giả gắn annotation.

Nhưng **bound chỉ là ràng buộc về quan hệ kiểu**, không bảo đảm class có constructor không đối số, không trừu tượng, không bị cấm truy cập hoặc không ném exception khi khởi tạo. Khi muốn thực sự tạo instance, phải thực hiện bằng code và xử lý lỗi reflection. Ví dụ đầy đủ sẽ gọi `getDeclaredConstructor().newInstance()` với hai renderer public/no-arg theo thiết kế.

## 5. Giá trị default: khai báo một lần, sử dụng ở nhiều nơi

Java dùng cú pháp:

```java
@interface Versioned {
    int revision() default 1;
    String[] tags() default {};
    Class<?> related() default Void.class;
}
```

Ý nghĩa:

- Nếu tác giả không ghi `revision`, accessor trả `1`.
- Nếu tác giả không ghi `tags`, accessor trả một mảng rỗng.
- Nếu tác giả không ghi `related`, accessor trả `Void.class`.

Một default phải là annotation element value hợp lệ với kiểu khai báo; không phải biểu thức Java runtime tùy ý. Với primitive/`String`, yêu cầu constant expression phù hợp; với `Class` thường dùng class literal; với enum dùng tên hằng trực tiếp; với mảng dùng `{...}` đúng cú pháp.

Các lựa chọn không hợp lệ:

```java
// @interface InvalidDefaults {
//     String now() default java.time.Instant.now().toString();
//     Class<?> current() default Class.forName("java.lang.String");
//     String optional() default null;
// }
```

Cả ba đều không phải cách cung cấp default annotation hợp lệ. Những cấu hình phụ thuộc thời gian, dữ liệu ngoài hoặc biến runtime phải để **consumer** tính lúc xử lý.

### Giá trị mặc định không phải giá trị copy vào mỗi lần sử dụng

JLS §9.6.2 chỉ rõ default của annotation element nằm trong **khai báo annotation interface**, và khi đọc annotation, giá trị default được áp dụng động nếu lần sử dụng không ghi tường minh. Điều này có hệ quả bảo trì:

- `@DocInfo(title="Quick start")` không chứa một bản sao mọi element default như các attribute được người viết ghi.
- Nếu library thay đổi `state() default DRAFT` thành `state() default REVIEW`, các lần sử dụng annotation cũ không ghi `state` có thể được phản chiếu với default mới khi dùng định nghĩa annotation tương ứng.
- Vì vậy **đổi default là một thay đổi hợp đồng**, có thể ảnh hưởng hành vi hệ thống ngay cả khi không sửa source của các class được gắn annotation.

Trong ứng dụng thực tế, hãy thận trọng khi thay đổi default đã được nhiều module phụ thuộc. Nếu một default mang ý nghĩa nghiệp vụ quan trọng, phải có test phát hiện tác động.

## 6. @Retention, @Target và @Documented cho DocInfo

Khi muốn xem metadata bằng Java reflection lúc chương trình chạy:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface DocInfo { /* elements... */ }
```

- `@Retention(RUNTIME)` cho phép metadata của lần gắn annotation được lưu và phản chiếu ở runtime.
- `@Target(TYPE)` cho phép đặt trên khai báo class/interface tương ứng.
- `@Target(METHOD)` cho phép mô tả method API.
- `@Documented` có thể được thêm vào **định nghĩa annotation** khi muốn các công cụ Javadoc chuẩn ghi nhận lần gắn annotation trong tài liệu phần tử tương ứng.

Đừng nhầm `@Documented` với việc tự sinh website hoặc tự kiểm tra nội dung. Nó chỉ ảnh hưởng cách annotation được đưa vào Java documentation theo hợp đồng.

Nếu bỏ `@Retention`, mặc định là `RetentionPolicy.CLASS`, lúc đó `SomeClass.class.getAnnotation(DocInfo.class)` trong Java reflection thông thường có thể trả `null`. Nếu dùng annotation processor lúc biên dịch thay vì runtime reflection, SOURCE/CLASS cũng có thể phù hợp tùy kiến trúc. Bài này cần đọc metadata **lúc chạy**, nên chọn RUNTIME.

Nếu chỉ muốn gắn metadata trên class, có thể thu hẹp `@Target(ElementType.TYPE)`; cho phép nhiều vị trí hơn nhu cầu có thể khiến dữ liệu xuất hiện ngoài nơi consumer đang quét.

## 7. Ví dụ Java 17+ đầy đủ, chạy được

Tạo file duy nhất **DocumentInfoDemo.java**:

```java
import java.lang.annotation.*;
import java.util.*;

enum DocState { DRAFT, REVIEW, PUBLISHED }

interface Renderer {
    String render(String title);
}

class PlainRenderer implements Renderer {
    public String render(String title) {
        return "PLAIN: " + title;
    }
}

class HtmlRenderer implements Renderer {
    public String render(String title) {
        return "<h1>" + title + "</h1>";
    }
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface DocInfo {
    String title();
    DocState state() default DocState.DRAFT;
    Class<? extends Renderer> renderer() default PlainRenderer.class;
    Class<?> related() default Void.class;
    int revision() default 1;
    String[] tags() default {};
}

@DocInfo(
    title = "API guide",
    state = DocState.PUBLISHED,
    renderer = HtmlRenderer.class,
    related = String.class,
    revision = 2,
    tags = {"java", "api"}
)
class ApiGuide {}

@DocInfo(title = "Quick start")
class QuickStart {}

public class DocumentInfoDemo {
    static void print(Class<?> type) throws ReflectiveOperationException {
        DocInfo info = type.getAnnotation(DocInfo.class);
        if (info == null) {
            System.out.println("No metadata");
            return;
        }

        Renderer renderer =
                info.renderer().getDeclaredConstructor().newInstance();

        System.out.println(type.getSimpleName() + ": "
                + info.title() + ", " + info.state()
                + ", revision=" + info.revision());
        System.out.println("renderer=" + renderer.render(info.title()));
        System.out.println("related=" + info.related().getSimpleName());
        System.out.println("tags=" + Arrays.toString(info.tags()));
    }

    public static void main(String[] args) throws Exception {
        print(ApiGuide.class);
        print(QuickStart.class);

        System.out.println("default state="
                + DocInfo.class.getMethod("state").getDefaultValue());
        System.out.println("default related="
                + (DocInfo.class.getMethod("related").getDefaultValue()
                    == Void.class));
    }
}
```

Biên dịch bằng JDK 17+ và chạy:

```bash
javac --release 17 -Xlint:all DocumentInfoDemo.java
java DocumentInfoDemo
```

**Kết quả chính xác:**

```text
ApiGuide: API guide, PUBLISHED, revision=2
renderer=<h1>API guide</h1>
related=String
tags=[java, api]
QuickStart: Quick start, DRAFT, revision=1
renderer=PLAIN: Quick start
related=Void
tags=[]
default state=DRAFT
default related=true
```

Những điều đáng quan sát:

1. `ApiGuide` ghi tất cả element; renderer được chọn là `HtmlRenderer`, nên đầu ra chứa thẻ HTML.
2. `QuickStart` chỉ ghi `title`; mọi element còn lại có default, vì vậy trạng thái là `DRAFT`, renderer là `PlainRenderer`, số revision là `1`, tags rỗng.
3. `related=Void` là sentinel mà ta đã quy ước, **không phải** một “lớp đang được tài liệu tham chiếu”. Nếu consumer muốn thể hiện thông tin thân thiện, nó có thể đổi sentinel thành chuỗi `"(none)"`.
4. `DocInfo.class.getMethod("state").getDefaultValue()` đọc đúng default ngay trên khai báo annotation element; giá trị trả về là `DocState.DRAFT`.
5. `renderer()` trả **Class token**, không trả sẵn đối tượng renderer. Lệnh `getDeclaredConstructor().newInstance()` mới thực sự tạo instance. Với một class không có constructor phù hợp hoặc bị hạn chế quyền truy cập, consumer phải báo lỗi hoặc xử lý ngoại lệ.
6. `Arrays.toString(info.tags())` in mảng theo thứ tự; không nên dùng trực tiếp `info.tags().toString()` để mong thấy phần tử mảng.

Ví dụ đã sử dụng cả `String`, enum, class token có bound, class token không bound, primitive, mảng và default — đúng phạm vi của một annotation mô tả tài liệu.

## 8. Đọc metadata của method, không chỉ class

Vì `@Target` của `DocInfo` cho phép cả `METHOD`, bạn có thể ghi:

```java
class DocumentApi {
    @DocInfo(title = "Find document", state = DocState.PUBLISHED)
    public String find(int id) {
        return "doc-" + id;
    }
}
```

Đoạn này dựa trên các kiểu `DocInfo`/`DocState` đã khai báo ở ví dụ, không phải file độc lập. Cách đọc:

```java
var method = DocumentApi.class.getDeclaredMethod("find", int.class);
DocInfo doc = method.getAnnotation(DocInfo.class);
System.out.println(doc.title());
```

Tương ứng sẽ in `Find document`. Việc đặt `@DocInfo` trên method **không tự tạo endpoint API**, không giúp framework HTTP tự phát hiện route và không sinh JavaDoc hoàn chỉnh. Consumer cần chủ động quét những method mình quan tâm.

Lưu ý tên method và parameter types phải khớp khi gọi `getDeclaredMethod`; nếu không sẽ gặp `NoSuchMethodException`. Nếu metadata thuộc một method được thừa kế, `getDeclaredMethod` và `getMethod` có phạm vi tìm khác nhau. `@Inherited` cũng không tự lan qua method override. Chúng là các quy tắc Java reflection riêng với việc định nghĩa annotation element.

## 9. Dùng Class token để chọn renderer: chỗ nào an toàn, chỗ nào chưa?

Khai báo:

```java
Class<? extends Renderer> renderer()
        default PlainRenderer.class;
```

đảm bảo class token được gắn thỏa quan hệ kiểu. Điều này tốt hơn khai báo `String rendererClassName()` trong nhiều tình huống vì compiler kiểm tra được mức tối thiểu: tên class có tồn tại và class có tương thích `Renderer` không.

Tuy nhiên Java không tự suy ra những bảo đảm bổ sung:

| Điều mong muốn | Class bound có bảo đảm? | Cần thêm gì? |
|---|---|---|
| Implementation có quan hệ kiểu với `Renderer` | Có, theo luật kiểu của class token | Không cần kiểm tra kiểu thủ công cơ bản |
| Có constructor không tham số | Không | Reflection validation hoặc convention/build-time processor |
| Constructor có thể truy cập được | Không | Quy tắc public/accessibility; xử lý lỗi |
| Renderer không phải abstract/interface | Không | Kiểm tra `Modifier.isAbstract` và khả năng instantiation |
| Kết quả `render(...)` an toàn để chèn HTML | Không | Escaping/encoding phù hợp khi sử dụng |
| Renderer thread-safe | Không | Thiết kế component/lifecycle riêng |
| Class có thể được nạp trong môi trường runtime thực tế | Không tuyệt đối | Đảm bảo dependency runtime và packaging hợp lệ |

Trong thí nghiệm, `PlainRenderer` và `HtmlRenderer` có constructor không đối số mà code trong cùng phạm vi có thể truy cập. Trong một framework lớn, có thể thay reflection bằng một registry hoặc dependency injection container để kiểm soát lifecycle, caching và quyền truy cập.

Ví dụ nếu người dùng chọn `Renderer.class` (interface chính), giá trị **hợp lệ theo bound** nhưng `getDeclaredConstructor().newInstance()` sẽ không khởi tạo được. Do đó consumer cần validation nếu hành vi runtime đòi một concrete class.

## 10. Những lỗi compile-time nên nhận biết

Một số ví dụ sai được **comment** để toàn bộ lesson vẫn có phần chương trình chính compile được:

### Bỏ element bắt buộc

```java
// @DocInfo
// class MissingTitle {}
```

`DocInfo.title()` không có default, nên bắt buộc cung cấp khi dùng annotation.

### Enum sai kiểu hoặc sai hằng

```java
// @DocInfo(title = "Guide", state = "PUBLISHED")
// class WrongStateType {}
//
// @DocInfo(title = "Guide", state = DocState.PUBLISH)
// class UnknownEnumConstant {}
```

Cách đúng là `DocState.PUBLISHED`.

### Class không thỏa bound

```java
// @DocInfo(title = "Guide", renderer = String.class)
// class WrongRenderer {}
```

`String` không triển khai `Renderer`, nên không phù hợp với `Class<? extends Renderer>`.

### Giá trị element không phải constant được chấp nhận

```java
// @DocInfo(title = System.getenv("DOC_TITLE"))
// class RuntimeTitle {}
```

Giá trị `title` cần là compile-time constant expression phù hợp; không thể gọi `System.getenv` để tính tên tài liệu ngay tại vị trí dùng annotation.

### Null, collection và mảng sai kiểu

```java
// @DocInfo(title = null)
// class NullTitle {}
//
// @DocInfo(title = "Guide", tags = {1, 2})
// class IntegerTags {}
```

Java không chấp nhận `null` làm annotation value và không cho `int` vào element `String[]`.

### Nhầm cú pháp mảng một phần tử và mảng rỗng

```java
@DocInfo(title = "One tag", tags = {"java"})
class OneTag {}

@DocInfo(title = "One tag shorthand", tags = "java")
class OneTagShorthand {}

@DocInfo(title = "No tags", tags = {})
class NoTags {}
```

Khi annotation element có kiểu mảng, cú pháp một phần tử có thể bỏ ngoặc nhọn như `tags = "java"`; nhưng nó **vẫn là mảng một phần tử** khi đọc. Mảng rỗng `{}` là một giá trị khác.

## 11. Default khác “giá trị thiếu” và khác sentinel

Với `DocInfo`, ta có:

```java
Class<?> related() default Void.class;
```

Đây là quy ước **không có class liên quan**. Nó không phải tương đương chung của `null`, cũng không khiến accessor có thể trả `null` từ một annotation hợp lệ. Consumer nên định nghĩa một predicate rõ:

```java
boolean hasRelatedClass = info.related() != Void.class;
```

Nếu dự án có use case thật sự muốn mô tả `Void.class` như một giá trị domain, sentinel này sẽ gây nhập nhằng và nên thay bằng một enum hoặc cấu trúc annotation khác. Không có sentinel tốt cho mọi ứng dụng.

Với element mảng:

```java
String[] tags() default {};
```

tập rỗng có thể được hiểu là “chưa phân loại”. Nếu cần phân biệt “người dùng chủ động đặt mảng rỗng” với “người dùng không ghi tags”, **giá trị annotation đọc được không cung cấp một cờ provenance chung**. Hai cách ghi `tags={}` và không ghi `tags` cùng giải ra mảng rỗng và cùng ý nghĩa dưới `Annotation.equals`. Muốn phân biệt mức ý nghĩa này, phải thay đổi thiết kế dữ liệu/hợp đồng công cụ.

## 12. Có nên dùng annotation thay thế mọi file cấu hình?

Annotation phù hợp cho **metadata bám vào một declaration và thay đổi cùng source code**. Dùng nó khi:

- Người đọc cần mô tả trực tiếp class/method/API.
- Các kiểu giá trị trong annotation đủ để mô hình hóa dữ liệu.
- Metadata có giá trị ở compile time hoặc runtime tùy retention.
- Muốn IDE/compiler trợ giúp phát hiện typo về kiểu.

Không nên ép annotation chứa **nội dung tài liệu dài, bản dịch, HTML động, URL nhạy cảm, khóa bí mật hoặc trạng thái môi trường runtime**. Những dữ liệu này có thể phù hợp với resource file, database, config service hoặc tập tin tài liệu riêng. Annotation cũng không tự cập nhật khi trạng thái bên ngoài đổi.

Một giải pháp kết hợp: `@DocInfo` ghi metadata cơ bản, còn consumer tra kho tài liệu thực tế theo `title` hoặc ID. Nếu xây generator, annotation processor có thể dùng metadata để sinh index docs trong quá trình biên dịch; nếu xây runtime UI, reflection có thể đọc metadata và render bằng code đã viết.

## 13. Kiểm thử annotation: cần kiểm tra những gì?

Với bài tổng hợp, test nên có ít nhất:

1. **Annotation hiện diện:** `type.getAnnotation(DocInfo.class) != null` ở nơi có gắn annotation.
2. **Giá trị bắt buộc:** `title()` đúng nội dung cung cấp.
3. **Enum default:** `QuickStart.state() == DocState.DRAFT`.
4. **Class bound:** `renderer()` là class tương thích `Renderer`; với dữ liệu cụ thể, kiểm tra có renderer mong muốn.
5. **Class token sentinel:** `related() == Void.class` khi không ghi.
6. **Primitive default:** `revision() == 1`.
7. **Mảng:** `Arrays.equals(tags, expectedTags)` thay vì gọi `tags.equals(...) `.
8. **Runtime consumer:** instantiate renderer và xác minh output dự kiến hoặc một lỗi được báo rõ.
9. **Missing metadata:** consumer có chính sách xử lý khi `getAnnotation` trả `null`.
10. **Negative compile samples:** thiếu title, sai enum, sai class bound và expression không constant phải thất bại đúng lý do.

Có thể viết kiểm thử trực tiếp không cần JUnit:

```java
DocInfo quick = QuickStart.class.getAnnotation(DocInfo.class);
if (quick == null || quick.state() != DocState.DRAFT) {
    throw new AssertionError("Incorrect default state");
}
if (!Arrays.equals(quick.tags(), new String[0])) {
    throw new AssertionError("Incorrect default tags");
}
```

Đoạn trên dùng các loại đã được khai báo ở chương trình chính và đặt trong một method/test hợp lệ. Với Maven/Gradle, nên đưa các assertion quan trọng vào `src/test/java` và chạy bằng test runner tương ứng để chúng không bị bỏ qua trên CI.

### Khi nào viết annotation processor cho DocInfo?

Nếu cần **từ chối class** khi `title` rỗng hoặc `revision <= 0`, có thể viết một processor:

```java
for (Element e : roundEnv.getElementsAnnotatedWith(DocInfo.class)) {
    DocInfo doc = e.getAnnotation(DocInfo.class);
    if (doc.title().isBlank() || doc.revision() <= 0) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR, "Invalid document metadata", e);
    }
}
```

Đây là **đoạn minh họa trong method process của processor**, cần import, processor setup và annotation API. Compiler Java thuần không tự có điều kiện đó. Processor sẽ thực thi lúc compilation **nếu được cấu hình chạy**; chọn SOURCE/CLASS/RUNTIME cho DocInfo theo yêu cầu tiêu thụ thực tế.

## 14. Annotation equality, hashCode và mảng khi kiểm tra metadata

Java định nghĩa equality của annotation theo **cùng annotation interface và từng element value**, bao gồm những element dùng giá trị mặc định.

Hai lần dùng:

```java
@DocInfo(title="A")
class A {}

@DocInfo(
    title="A",
    state=DocState.DRAFT,
    renderer=PlainRenderer.class,
    related=Void.class,
    revision=1,
    tags={}
)
class B {}
```

sẽ tương đương về mặt `Annotation.equals`: cùng type `DocInfo` và cùng mọi giá trị resolved. Việc ghi đủ các default tường minh không làm kết quả khác.

Mảng `tags` được so **theo nội dung và thứ tự** bằng `Arrays.equals`, không phải theo tham chiếu. Do đó `{"java","api"}` và `{"api","java"}` không bằng nhau ở một annotation element dạng mảng.

`hashCode` của annotation cũng được quy định phù hợp với `equals`. Tuy nhiên đừng dùng `annotation.toString()` làm định dạng dữ liệu ổn định để ghi file; định dạng chuỗi cụ thể có thể khác giữa implementation.

## 15. Cách mở rộng mô hình mà vẫn tuân thủ Java

**Thêm metadata tác giả:** có thể thêm `String author() default "unknown";`. Thay default chỉ nên làm khi đã hiểu tác động tới các lần dùng cũ.

**Thêm loại renderer:** triển khai thêm class `MarkdownRenderer implements Renderer`, rồi dùng `renderer = MarkdownRenderer.class`. Không cần đổi annotation interface vì bound đã cho phép implementation mới.

**Thêm nhiều related classes:** dùng `Class<?>[] relatedTypes() default {};`, với cú pháp `relatedTypes = {String.class, Number.class}`. Không tạo `List<Class<?>>` làm annotation element vì không hợp lệ.

**Thêm metadata nested:** định nghĩa một annotation riêng:

```java
@interface Author {
    String name();
    String team() default "docs";
}
```

rồi thêm element:

```java
// Nằm trong định nghĩa @interface DocInfo:
Author author() default @Author(name = "unknown");
```

`Author` là annotation type hợp lệ để làm element; `@Author(...)` là annotation value, không phải đối tượng được khởi tạo bằng `new`. Nếu dùng nested annotation để tạo cấu trúc phức tạp, vẫn phải tôn trọng các giới hạn element type và default, không có collection tùy ý.

**Thay phạm vi:** nếu cần mô tả package hoặc module, cân nhắc `ElementType.PACKAGE`/`MODULE` và cách khai báo annotation tương ứng. Không nên âm thầm mở rộng `@Target` quá mức nếu consumer không hỗ trợ.

## 16. Những hiểu nhầm thường gặp

- **“Class token đã tạo đối tượng.”** Sai. `HtmlRenderer.class` chỉ là class token; tạo đối tượng cần code và quyền truy cập.
- **“Enum tự bảo đảm workflow xuất bản.”** Sai. Enum chỉ xác định danh sách giá trị được phép, không tự triển khai transition.
- **“Default là null khi không ghi.”** Sai. Phải có default rõ hoặc bắt buộc gắn giá trị; `null` không phải annotation element value hợp lệ.
- **“Không ghi revision thì annotation thiếu element.”** Sai. `default 1` được áp dụng khi đọc.
- **“Class<? extends Renderer> bảo đảm có public constructor.”** Sai. Bound là quan hệ kiểu; instantiation có điều kiện riêng.
- **“Có @DocInfo thì Javadoc tự thành trang tài liệu hoàn chỉnh.”** Sai. `@Documented` chỉ hỗ trợ cơ chế ghi nhận annotation theo Javadoc.
- **“@Retention(CLASS) đọc được qua getAnnotation lúc chạy.”** Sai trong reflection thông thường; bài chạy ví dụ cần RUNTIME.
- **“Có title rồi thì không bao giờ rỗng.”** Sai. `title=""` vẫn hợp lệ về kiểu; cần validation riêng nếu không cho phép.
- **“tags là Set không thứ tự.”** Sai. `String[]` giữ thứ tự phần tử; `Arrays.equals` cũng xét thứ tự.
- **“Đổi default vô hại với các class đã compile.”** Không nhất thiết: default đọc từ khai báo annotation hiện hành nên có thể thay đổi giá trị resolved.

## 17. Bài tập thực hành

### Bài 1 — Kiểu enum

Thêm trạng thái `DEPRECATED` vào `DocState`. Viết `@DocInfo(title="Old API", state=DocState.DEPRECATED)`. Tại sao compiler cho biết ngay nếu bạn gõ sai hằng?

**Gợi ý đáp án:** `state()` là enum `DocState`, nên compiler phải tìm đúng enum constant tương thích. Chuỗi bất kỳ không được chấp nhận.

### Bài 2 — Default

Gắn `@DocInfo(title="Intro")` lên một class khác. Hỏi kết quả `revision()`, `tags()` và `renderer()`?

**Đáp án:** `1`, mảng rỗng, `PlainRenderer.class`. Đây là default của annotation interface.

### Bài 3 — Class bound

Có `class PdfRenderer implements Renderer`. Có thể dùng `renderer=PdfRenderer.class` không? Còn `renderer=String.class`?

**Đáp án:** `PdfRenderer.class` hợp lệ; `String.class` không triển khai `Renderer` nên không thỏa bound.

### Bài 4 — Sentinel

Vì sao dùng `Void.class` để biểu diễn “không có related class” thay vì `null`?

**Đáp án:** Java không cho `null` làm annotation value; `Void.class` là class literal hợp lệ. Sentinel là quy ước riêng phải được consumer hiểu.

### Bài 5 — Consumer runtime

Nếu `getAnnotation(DocInfo.class)` trả `null`, phương thức `print` trong ví dụ xử lý thế nào?

**Đáp án:** in `No metadata` rồi return, không dereference `null`.

### Bài 6 — Renderer không khởi tạo được

Nếu `renderer()` trỏ tới một abstract class triển khai `Renderer`, annotation có compile không? Reflection có tạo instance không?

**Đáp án:** class token có thể thỏa bound ở compile time, nhưng abstract class không thể được khởi tạo bằng constructor reflection theo cách demo, vì vậy consumer phải phát hiện/xử lý.

### Bài 7 — Mảng một phần tử

Viết `tags="java"` thay cho `tags={"java"}` có thay đổi kiểu trả về `tags()` không?

**Đáp án:** không. Accessor luôn trả `String[]`; đó là cú pháp rút gọn cho một phần tử.

### Bài 8 — Dùng trong CI

Muốn cấm tiêu đề chỉ có dấu cách, phải sửa gì?

**Đáp án:** thêm logic validation vào consumer/processor phù hợp, ví dụ `title().isBlank()` và phát `Diagnostic.Kind.ERROR` ở compile time hoặc ném một exception rõ ràng khi runtime consumer đọc metadata.

### Bài 9 — Default thay đổi

Nếu đổi `revision() default 1` thành `default 2`, `@DocInfo(title="Quick start")` có thể đọc được phiên bản mới thế nào?

**Đáp án:** nếu không ghi revision tường minh, giá trị default của định nghĩa annotation mới có thể được áp dụng khi đọc. Đây là thay đổi hợp đồng cần review và test.

### Bài 10 — Nested metadata

Thiết kế `@Author(name="Alice", team="docs")` làm một element kiểu `Author` của `@DocInfo` có hợp lệ không?

**Đáp án:** có, vì Java cho phép một annotation interface type làm kiểu của element. Chỉ cần khai báo `Author` và `default`/giá trị đúng cú pháp.

## 18. Checklist hoàn thành bài thực hành

- [ ] Có một `enum DocState` với các trạng thái rõ nghĩa.
- [ ] Có interface `Renderer` và ít nhất hai implementation.
- [ ] `DocInfo` sử dụng `Class<?> ` cho class không ràng buộc và `Class<? extends Renderer>` cho renderer.
- [ ] Element `title()` bắt buộc, các element còn lại có default.
- [ ] `@Retention(RUNTIME)` vì ví dụ đọc bằng reflection runtime.
- [ ] `@Target` chỉ cho phép những vị trí mà consumer hỗ trợ.
- [ ] `ApiGuide` gắn giá trị tường minh; `QuickStart` gắn tối giản.
- [ ] `javac --release 17 -Xlint:all` compile thành công.
- [ ] Output của `DocumentInfoDemo` khớp với ví dụ.
- [ ] Có negative tests cho thiếu title, enum sai, class bound sai.
- [ ] Không giả định annotation tự sinh tài liệu hoặc áp đặt validation nghiệp vụ.

### Tài liệu tham khảo

- [JLS Java SE 17 — §9.6 Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): các element types được phép trong annotation.
- [JLS Java SE 17 — §9.6.2 Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2): ngữ nghĩa default, bao gồm việc áp dụng khi đọc.
- [JLS Java SE 17 — §9.7.1 Normal Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): bắt buộc cung cấp giá trị nếu element không có default.
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): thời điểm annotation còn được giữ.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class token và các thao tác reflection.
- [Java SE 17 — Annotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html): interface chung và hợp đồng `annotationType`, `equals`, `hashCode`.

**Kết luận:** khi mô tả thông tin tài liệu bằng annotation, **enum** biểu diễn các lựa chọn hữu hạn, **Class token** biểu diễn một kiểu đã được compiler biết, và **default** giúp nơi sử dụng ngắn gọn. Consumer quyết định hành vi dựa trên metadata. Giới hạn của annotation type và class bound là điều kiện compile-time; các điều kiện nghiệp vụ sâu hơn cần được kiểm tra chủ động.
