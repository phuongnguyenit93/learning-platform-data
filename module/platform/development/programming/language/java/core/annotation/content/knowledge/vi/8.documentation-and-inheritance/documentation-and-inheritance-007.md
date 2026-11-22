# Meta-annotation tùy chỉnh và giới hạn của xử lý bắc cầu trong Java Core

Một **meta-annotation** là annotation được gắn lên **khai báo của một annotation khác**. Nó cho phép mô tả annotation đó: đặt nơi được sử dụng bằng `@Target`, thời điểm lưu metadata bằng `@Retention`, hoặc bổ sung một quy ước riêng cho ứng dụng. Từ đó, lập trình viên có thể tạo *annotation tổng hợp* (*composed annotation*) như `@GetReports` được gắn sẵn `@Route(method = "GET", path = "/reports")`.

Điểm quan trọng nhất: **Java Core không có quy tắc chung tự động chuyển meta-annotation thành annotation của class, method hoặc field đang dùng annotation tổng hợp**. Reflection chuẩn chỉ trả lại annotation theo đúng ngữ nghĩa của `AnnotatedElement`; nếu muốn suy luận gián tiếp từ `@GetReports` sang `@Route`, người viết công cụ hoặc framework phải triển khai logic tra cứu đó.

Ví dụ khái quát:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Route {
    String method();
    String path();
}

@Route(method = "GET", path = "/reports")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface GetReports {}

@GetReports
class ReportController {}
```

- `ReportController` được gắn **trực tiếp** `@GetReports`.
- **Kiểu annotation** `GetReports` được gắn **trực tiếp** `@Route`.
- `ReportController.class.getAnnotation(Route.class)` trả về `null`. `@Route` không tự “chảy” xuống `ReportController`.
- `GetReports.class.getAnnotation(Route.class)` trả về một `Route` vì đó mới là nơi `@Route` được gắn.

Sự khác biệt giữa **annotation trên phần tử**, **meta-annotation trên kiểu annotation**, **kế thừa `@Inherited`**, và **cơ chế framework tự dò/ghép** là trọng tâm bài học.

## 1. Meta-annotation tùy chỉnh là gì?

Java có những meta-annotation chuẩn:

| Meta-annotation | Công dụng chính |
|---|---|
| `@Target` | Giới hạn nơi có thể gắn annotation |
| `@Retention` | Xác định annotation được giữ đến SOURCE, CLASS hay RUNTIME |
| `@Documented` | Yêu cầu công cụ Javadoc ghi nhận annotation ở tài liệu phần tử được gắn |
| `@Inherited` | Cho phép kế thừa annotation theo superclass trong tình huống Java định nghĩa |
| `@Repeatable` | Khai báo một annotation có thể xuất hiện nhiều lần trên cùng phần tử, dùng annotation chứa |

Ta cũng có thể tự định nghĩa một annotation dùng làm meta-annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface FeatureGroup {
    String value();
}

@FeatureGroup("operations")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface BatchJob {}

@BatchJob
class NightlyJob {}
```

`FeatureGroup` mô tả **annotation type** `BatchJob`, còn `BatchJob` mô tả **class** `NightlyJob`.

Có thể hình dung:

```text
NightlyJob.class
    |
    | trực tiếp có
    v
@BatchJob
    |
    | BatchJob.class trực tiếp có
    v
@FeatureGroup("operations")
```

Đây là quan hệ hai tầng trong metadata. Trong Java Core, không có luật nào biến hình vẽ đó thành quan hệ trực tiếp `@FeatureGroup` trên `NightlyJob`. Khi thiết kế một framework, việc coi `@BatchJob` đồng nghĩa một loại feature group là **quy ước riêng**, do framework cần lập trình.

## 2. Phân biệt ba khái niệm dễ nhầm

**Annotation trực tiếp (direct annotation):** annotation thực sự được gắn trên phần tử đang xét.

```java
@BatchJob
class NightlyJob {}
```

`NightlyJob.class.getDeclaredAnnotation(BatchJob.class)` tìm được `BatchJob`, còn `NightlyJob.class.getDeclaredAnnotation(FeatureGroup.class)` trả về `null`.

**Meta-annotation:** annotation được gắn trên khai báo của một annotation type:

```java
@FeatureGroup("operations")
@interface BatchJob {}
```

`BatchJob.class.getDeclaredAnnotation(FeatureGroup.class)` có thể đọc được `FeatureGroup` nếu annotation này có retention RUNTIME.

**Tra cứu bắc cầu (transitive/composed lookup):** thuật toán tự viết hoặc một framework chủ động đi từ annotation trên phần tử tới annotation type của nó, rồi tiếp tục tìm các meta-annotation. Đây **không phải** hành vi mặc định của `Class.getAnnotation(...)`.

Khi dùng các thuật ngữ “có annotation”, “kế thừa”, “bắc cầu”, cần nêu rõ **đối tượng nào được hỏi và API/thuật toán nào đang hỏi**. Ví dụ: “`NightlyJob` có trực tiếp `BatchJob`” khác với “`BatchJob` được meta-annotated bởi `FeatureGroup`”.

## 3. Định nghĩa một meta-annotation tùy chỉnh đúng cách

Mẫu thường dùng:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Category {
    String value();
}
```

Ở đây:

- `@Target(ElementType.ANNOTATION_TYPE)` giới hạn nơi đặt `@Category` là khai báo annotation type, ví dụ `@interface QueryHandler`.
- `@Retention(RetentionPolicy.RUNTIME)` cho phép một công cụ dùng reflection đọc `@Category` trên `QueryHandler.class` khi chạy.
- `String value()` chứa dữ liệu của meta-annotation, chẳng hạn `"read-only"`.

Ví dụ sử dụng:

```java
@Category("read-only")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface QueryHandler {}

class QueryService {
    @QueryHandler
    String getStatus() {
        return "ready";
    }
}
```

Nếu đọc metadata qua Java reflection:

```java
// Minh họa trong một method có thể ném NoSuchMethodException:
var method = QueryService.class.getDeclaredMethod("getStatus");

QueryHandler direct = method.getAnnotation(QueryHandler.class);
Category meta = QueryHandler.class.getAnnotation(Category.class);

System.out.println(direct != null); // true
System.out.println(meta.value());    // read-only
System.out.println(method.getAnnotation(Category.class) == null); // true
```

Đoạn ngắn này minh họa trong ngữ cảnh nơi các kiểu đã được định nghĩa. Nó không phải một chương trình Java chạy độc lập; ví dụ đầy đủ nằm ở phần sau.

### Những điều `@Retention` và `@Target` không tự truyền qua lớp bọc

**Retention của meta-annotation không tự quy định retention của annotation tổng hợp.** Xét:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface MetaFlag {}

@MetaFlag
@Target(ElementType.TYPE)
@interface Flagged {}
```

`MetaFlag` có RUNTIME, nhưng `Flagged` **không tự có RUNTIME**: nếu không khai báo `@Retention`, `Flagged` dùng mặc định **CLASS**. Vì vậy `Flagged.class.getAnnotation(MetaFlag.class)` có thể thấy `MetaFlag`, trong khi class được gắn `@Flagged` không nhất thiết có thể truy vấn `Flagged` bằng reflection runtime. Muốn scan runtime, phải khai báo retention RUNTIME trên `Flagged`.

**Target của meta-annotation không tự trở thành target của annotation tổng hợp.** `@Target(ANNOTATION_TYPE)` trên `MetaFlag` chỉ giới hạn `MetaFlag`; nếu muốn `Flagged` chỉ dùng trên class thì cần đặt `@Target(TYPE)` ngay trên định nghĩa `Flagged`.

Tương tự, `@Documented` trên một meta-annotation không tự khiến một annotation tổng hợp được ghi vào Javadoc ở nơi sử dụng; annotation muốn được Javadoc ghi nhận phải tuân theo quy định của chính `@Documented`.

## 4. Ví dụ đầy đủ Java 17+: annotation tổng hợp và @Inherited

Tạo một file duy nhất tên **`MetaAnnotationDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Route {
    String method();
    String path();
}

@Route(method = "GET", path = "/reports")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface GetReports {}

@GetReports
class ReportController {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {}

@Audited
class BaseService {}

class ChildService extends BaseService {}

@Audited
interface AuditedContract {}

class ContractService implements AuditedContract {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {}

class BaseAction {
    @Traced
    public void act() {}
}

class ChildAction extends BaseAction {
    @Override
    public void act() {}
}

public class MetaAnnotationDemo {
    static Route findOneLevelRoute(Class<?> type) {
        for (Annotation direct : type.getDeclaredAnnotations()) {
            Route route = direct.annotationType().getAnnotation(Route.class);
            if (route != null) {
                return route;
            }
        }
        return null;
    }

    public static void main(String[] args) throws NoSuchMethodException {
        System.out.println("direct Route: "
                + ReportController.class.isAnnotationPresent(Route.class));
        System.out.println("direct GetReports: "
                + ReportController.class.isAnnotationPresent(GetReports.class));

        Route onAnnotationType = GetReports.class.getAnnotation(Route.class);
        System.out.println("meta Route: " + onAnnotationType.method()
                + " " + onAnnotationType.path());

        Route resolved = findOneLevelRoute(ReportController.class);
        System.out.println("resolved Route: " + resolved.method()
                + " " + resolved.path());

        System.out.println("child inherits Audited: "
                + ChildService.class.isAnnotationPresent(Audited.class));
        System.out.println("child declares Audited: "
                + (ChildService.class.getDeclaredAnnotation(Audited.class)
                        != null));
        System.out.println("interface propagates Audited: "
                + ContractService.class.isAnnotationPresent(Audited.class));
        System.out.println("override inherits Traced: "
                + ChildAction.class.getDeclaredMethod("act")
                        .isAnnotationPresent(Traced.class));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 -Xlint:all MetaAnnotationDemo.java
java MetaAnnotationDemo
```

Kết quả chuẩn:

```text
direct Route: false
direct GetReports: true
meta Route: GET /reports
resolved Route: GET /reports
child inherits Audited: true
child declares Audited: false
interface propagates Audited: false
override inherits Traced: false
```

Giải thích:

1. `@Route` không gắn trực tiếp lên `ReportController` nên truy vấn trực tiếp trả `false`; `@GetReports` có gắn trực tiếp nên trả `true`.
2. `GetReports.class.getAnnotation(Route.class)` hỏi **chính khai báo annotation type** và đọc được `GET /reports`.
3. `findOneLevelRoute(...)` là hàm do ta viết: đọc annotation trực tiếp của class, lấy `annotationType()`, rồi chủ động tìm `@Route` **ở đúng một tầng meta**. Vì vậy nó có thể suy ra route.
4. `@Audited` có `@Inherited` nên `ChildService` thấy nó qua superclass `BaseService`, dù `ChildService` không khai báo trực tiếp.
5. `ContractService` triển khai interface được gắn `@Audited`, nhưng `@Inherited` không đi qua quan hệ `implements`.
6. `@Traced` được gắn trên method của `BaseAction`. Method override ở `ChildAction` không nhận `@Traced` chỉ vì annotation type có `@Inherited`.

**Phạm vi của helper:** `findOneLevelRoute(...)` chỉ phục vụ tình huống đơn giản, **không tự dò nhiều tầng**, không tự kế thừa quy ước từ các superclass, không kiểm tra xung đột nếu có nhiều annotation cùng meta-annotated bởi `@Route`. Cần thiết kế rõ các quy tắc này nếu sử dụng cho ứng dụng thật.

## 5. Java reflection chuẩn thực sự tìm annotation như thế nào?

Java reflection có API `AnnotatedElement` được triển khai trên class, method, field và những thành phần phù hợp. Các phương thức thường gặp có ngữ nghĩa riêng:

| API | Dạng annotation nó tìm | Ghi chú |
|---|---|---|
| `getDeclaredAnnotation(A.class)` | Annotation `A` được gắn trực tiếp vào phần tử | Không tra qua superclass |
| `getAnnotation(A.class)` | Annotation `A` “present” theo định nghĩa Java | Có thể tính inheritance cho **class** và `A` có `@Inherited` |
| `getDeclaredAnnotations()` | Tất cả annotation được khai báo trực tiếp | Không tự khai triển meta-annotation |
| `getAnnotations()` | Các annotation “present” | Trên class, có thể gồm annotation được kế thừa |
| `getDeclaredAnnotationsByType(A.class)` | `A` trực tiếp hoặc gián tiếp thông qua **repeatable container** trên phần tử | Không tự dò meta-annotation tùy chỉnh |
| `getAnnotationsByType(A.class)` | Các `A` “associated” với phần tử | Hiểu repeatable container và trường hợp inheritance được định nghĩa |

Tên “indirectly present” trong tài liệu `AnnotatedElement` có nghĩa kỹ thuật liên quan tới **`@Repeatable` và container annotation**, không phải một thuật toán bất kỳ đọc `@A` rồi lần theo mọi meta-annotation nằm trên `A.class`.

Ví dụ:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("api")
@Tag("core")
class TaggedService {}
```

Nếu gọi `TaggedService.class.getAnnotationsByType(Tag.class)`, API trả hai `@Tag` nhờ cơ chế **repeatable container**. Điều này không chứng minh nó biết cách tìm `@Category` từ `@BatchJob`: hai chức năng có hợp đồng hoàn toàn khác nhau.

Đừng dựa vào thứ tự mảng `getDeclaredAnnotations()` để giải quyết ưu tiên cấu hình giữa các annotation độc lập; nếu framework cho nhiều annotation tương đương, nên xác định cơ chế thứ tự/xung đột một cách tường minh.

## 6. @Inherited là một ngoại lệ có giới hạn, không phải cơ chế bắc cầu chung

`@Inherited` được khai báo trên **annotation type**, ví dụ:

```java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
}

@Policy("strict")
class Parent {}

class Child extends Parent {}
```

Truy vấn:

```java
boolean inherited = Child.class.isAnnotationPresent(Policy.class);
Policy declared = Child.class.getDeclaredAnnotation(Policy.class);
```

Ở đây `inherited == true` và `declared == null`. Java tìm tới superclass khi class con không có annotation tương ứng và loại annotation có `@Inherited`. Nó **không** thay đổi mã nguồn, không sao chép một annotation vật lý vào class con, và không tự tạo annotation khác.

Các giới hạn quan trọng:

- **Chỉ theo superclass của class:** class implements một interface có `@Policy` không tự nhận `@Policy` từ interface qua `@Inherited`.
- **Không tự kế thừa trên method:** nếu method được override, annotation của method cha không tự chuyển sang method con, dù annotation type được đánh dấu `@Inherited`.
- **Không làm annotation tổng hợp bắc cầu:** nếu một annotation A có meta-annotation B, `@Inherited` không tự khiến `getAnnotation(B.class)` trên class dùng A suy ra B.
- **Phải biết annotation nào được kế thừa:** `@Inherited` gắn trên chính annotation type cần cho cơ chế Java nhận từ superclass; gắn lên một annotation liên quan ở tầng meta không tự cấp hiệu lực kế thừa cho annotation tổng hợp khác.

Khi class con khai báo trực tiếp chính annotation type `Policy`, truy vấn thông thường dùng annotation của class con thay vì tiếp tục lấy instance đó ở superclass. Đây là cơ chế tìm theo một **loại annotation cụ thể**, không phải hợp nhất giá trị tất cả annotation cùng loại ở mọi tầng.

## 7. Một tầng meta và nhiều tầng meta khác nhau ra sao?

Xét các khai báo minh họa sau (mỗi annotation có RUNTIME để phục vụ reflection):

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface SecurityBoundary {}

@SecurityBoundary
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface InternalFeature {}

@InternalFeature
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InternalController {}

@InternalController
class BillingController {}
```

Đường đi là:

```text
BillingController
    -> @InternalController          (annotation trực tiếp)
        -> @InternalFeature         (meta-annotation cấp 1)
            -> @SecurityBoundary   (meta-annotation cấp 2)
```

Với reflection chuẩn:

- `BillingController.class.getAnnotation(SecurityBoundary.class)` là `null`.
- `InternalController.class.getAnnotation(InternalFeature.class)` đọc được annotation cấp 1.
- `InternalFeature.class.getAnnotation(SecurityBoundary.class)` đọc được annotation cấp tiếp theo.
- `InternalController.class.getAnnotation(SecurityBoundary.class)` **vẫn là `null`**: reflection không tự đi qua `InternalFeature`.

Một helper dò đúng **một tầng** như `findOneLevelRoute` sẽ không tìm `@SecurityBoundary` nếu bắt đầu từ `BillingController`; muốn đi tới nó phải có thuật toán dò nhiều tầng.

Đây là ý nghĩa của “giới hạn xử lý bắc cầu trong Java Core”: **metadata tạo thành quan hệ có thể duyệt**, nhưng **không có lời hứa rằng API chuẩn sẽ diễn giải hoặc hợp nhất chuỗi đó cho ứng dụng**.

## 8. Nếu tự viết bộ quét bắc cầu, cần quyết định điều gì?

Đối với nhu cầu chỉ kiểm tra *có tồn tại một loại meta-annotation trong đường đi hay không*, có thể viết thuật toán duyệt đồ thị annotation. Ví dụ minh họa dưới đây dùng API reflection và chặn đi lại một kiểu đã xét:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;
import java.util.HashSet;
import java.util.Set;

final class MetaScanner {
    static boolean hasMetaAnnotation(
            AnnotatedElement element,
            Class<? extends Annotation> sought) {
        Set<Class<? extends Annotation>> visited = new HashSet<>();
        for (Annotation direct : element.getDeclaredAnnotations()) {
            if (contains(direct.annotationType(), sought, visited)) {
                return true;
            }
        }
        return false;
    }

    private static boolean contains(
            Class<? extends Annotation> current,
            Class<? extends Annotation> sought,
            Set<Class<? extends Annotation>> visited) {
        if (!visited.add(current)) {
            return false;
        }
        if (current == sought) {
            return true;
        }
        for (Annotation meta : current.getDeclaredAnnotations()) {
            if (contains(meta.annotationType(), sought, visited)) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là **một utility có thể biên dịch** nếu lưu trong file cùng tên lớp hoặc dùng nó trong cùng source file phù hợp. Nó chỉ trả boolean và chỉ bắt đầu từ **các annotation khai báo trực tiếp** của phần tử đầu vào. Nó không chứa bất kỳ quy tắc nào để:

- kế thừa các annotation trên superclass/interface;
- đọc annotation có retention SOURCE hoặc CLASS từ reflection runtime;
- lựa chọn một giá trị cụ thể khi nhiều nhánh tìm tới annotation cùng loại;
- ghi đè/ghép attribute của annotation tầng ngoài và tầng trong;
- xác định mức ưu tiên giữa khai báo trực tiếp và khai báo bắc cầu;
- suy diễn annotation nào có nghĩa là cấu hình hợp lệ cho nghiệp vụ.

Tập `visited` giúp tránh duyệt lặp trong đồ thị meta-annotation; riêng việc **định nghĩa chính sách resolution** là phần quan trọng hơn một đoạn code DFS. Nếu chỉ cần duyệt một tầng, helper đơn giản ở ví dụ đầy đủ thường dễ kiểm soát hơn.

Khi sản phẩm cần composed annotations với nhiều thuộc tính tùy biến, alias hoặc quy tắc override, hãy tạo abstraction rõ ràng thay vì giả định rằng mọi hệ thống nên duyệt toàn bộ đồ thị annotation không phân biệt ý nghĩa.

## 9. Thuộc tính (element) không tự động được gộp hoặc “alias”

Giả sử:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Endpoint {
    String path();
}

@Endpoint(path = "/default")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface WebEndpoint {
    String value() default "/custom";
}

@WebEndpoint("/orders")
class OrderEndpoint {}
```

Từ Java Core ta có thể đọc:

- `OrderEndpoint.class.getAnnotation(WebEndpoint.class).value()` → `"/orders"`.
- `WebEndpoint.class.getAnnotation(Endpoint.class).path()` → `"/default"`.

**Không có quy tắc trong Java Core** để tự hiểu `WebEndpoint.value()` là alias của `Endpoint.path()` rồi biến `"/default"` thành `"/orders"`. Nếu framework muốn cho người dùng override đường dẫn qua `@WebEndpoint("/orders")`, nó phải khai báo và thực thi quy tắc chuyển giá trị này.

Tương tự, nếu hai annotation tổng hợp cùng xác định một endpoint nhưng khác method/path, Java không tự quyết định ưu tiên cái nào. Có thể báo lỗi, cấm kết hợp hoặc đặt một thứ tự rõ ràng. Đừng dựa vào thứ tự ngẫu nhiên của các annotation trả về từ một lần scan.

## 10. SOURCE, CLASS, RUNTIME tác động đến xử lý bắc cầu như thế nào?

Một scanner dùng Java reflection ở runtime chỉ thấy những annotation còn được giữ phù hợp với reflection. Nếu một tầng của chuỗi có retention SOURCE, lần sử dụng annotation ở tầng đó bị loại khỏi binary; với CLASS, runtime reflection chuẩn cũng không đọc được lần sử dụng đó.

| Vị trí trong chuỗi | Nếu là SOURCE/CLASS | Hệ quả khi dùng reflection runtime |
|---|---|---|
| Annotation tổng hợp gắn trên class, ví dụ `@GetReports` | SOURCE không lưu vào class; CLASS không được reflection hiện ra | Scanner runtime thường không bắt đầu được từ `@GetReports` |
| Meta-annotation gắn trên annotation type, ví dụ `@Route` trên `GetReports` | Nếu không phải RUNTIME, reflection không trả meta-annotation ở tầng đó | Không tìm thấy `@Route` qua `GetReports.class.getAnnotation(...)` |
| Annotation cần kết quả để đọc attribute | Attribute của loại không visible không tự truy xuất được qua reflection chuẩn | Phải chọn runtime metadata hoặc một artifact xử lý ở compile time |

Vì vậy khi thiết kế **runtime meta-annotation scanner**, các annotation cần nhìn thấy trên đường tìm kiếm thường phải có `@Retention(RUNTIME)` phù hợp. Với **annotation processing tại thời điểm biên dịch source**, processor có thể truy vấn mô hình compiler thay cho runtime reflection, nên điều kiện retention khác: nó vẫn có thể thấy SOURCE trong lượt compile đang xử lý.

Không nên đổi retention của tất cả annotation sang RUNTIME theo thói quen. Chọn thời điểm tiêu thụ metadata trước, sau đó chọn retention phù hợp với consumer thực tế.

## 11. Java Core và khả năng mở rộng của framework

Một framework có thể cố tình định nghĩa các annotation “kết hợp” để rút gọn cấu hình:

```text
@BusinessEndpoint
     |
     +-- meta: @Route
     |
     +-- meta: @AccessPolicy
     |
     +-- meta: @LoggingCategory
```

Nhưng để `@BusinessEndpoint` có ý nghĩa nghiệp vụ, framework cần triển khai cụ thể:

1. **Discovery:** tìm annotation nào trên class/method; xét có tra superclass/interface hay không.
2. **Meta traversal:** giới hạn một tầng hay đệ quy, có loại trừ meta-annotation chuẩn khỏi một số loại scan không.
3. **Attribute resolution:** chọn giá trị của tầng nào khi path, role, timeout bị định nghĩa nhiều lần.
4. **Conflict handling:** nhiều khai báo không tương thích thì báo lỗi hay chọn độ ưu tiên rõ ràng.
5. **Lifecycle:** đọc lúc compile time bằng annotation processor, hay runtime reflection, hay từ artifact đã sinh.

Chẳng hạn Spring Framework có các tiện ích riêng cho composed annotation và merged annotations. Đó là **hợp đồng của Spring**, không phải API hay đặc tính tự động của Java Core. Trong mã Java thuần, muốn có quy tắc tương tự cần xây dựng hoặc dùng thư viện có định nghĩa tương đương.

Không phải cứ thấy một annotation được meta-annotated bởi annotation khác thì mọi thư viện trong ứng dụng đều biết khai thác cấu trúc đó. Công cụ phải được viết để nhận diện.

## 12. Lỗi phổ biến và cách kiểm tra

**Lỗi 1 — Tưởng `getAnnotation` tự tìm meta-annotation trên class.**

```java
@Route(method = "GET", path = "/reports")
@interface GetReports {}

@GetReports
class ReportController {}
```

Truy vấn `ReportController.class.getAnnotation(Route.class)` không tìm thấy. Hãy hỏi `GetReports.class`, hoặc viết bộ quét riêng nếu thực sự muốn lấy `Route` thông qua `GetReports`.

**Lỗi 2 — Gắn `@Inherited` vào meta-annotation rồi mong annotation tổng hợp tự được kế thừa.**

Chỉ vì `@Route` có `@Inherited` không có nghĩa `@GetReports` sẽ tự được kế thừa bởi mọi class con. Nếu thật sự muốn annotation `GetReports` được phản chiếu từ superclass, phải đặt `@Inherited` lên **định nghĩa `GetReports`** và áp dụng nó ở class. Dù vậy, `@Route` vẫn không trở thành annotation trực tiếp của class con.

**Lỗi 3 — Nghĩ `@Inherited` áp dụng cho interface và method override.**

Nó chỉ hỗ trợ quan hệ superclass với annotation trên class như JDK quy định. Nếu cần quét interface hoặc method override, thuật toán của framework phải xử lý riêng; cần đặc biệt thận trọng khi một class có nhiều interface và các phương thức cùng tên.

**Lỗi 4 — Meta-annotation có RUNTIME nhưng annotation ngoài thiếu RUNTIME.**

Nếu annotation tổng hợp có retention mặc định CLASS, scanner runtime không thể nhìn thấy nó trên class như với RUNTIME. Mỗi annotation type trong đường đi cần được thiết kế retention riêng; không có cơ chế tự lan retention.

**Lỗi 5 — Nhầm `getAnnotationsByType` của repeatable với meta traversal.**

API này xử lý container của `@Repeatable`; nó không tự động dò `@A -> @B -> @C`. Tên thuật ngữ “indirectly present” trong Javadoc không có nghĩa bắc cầu meta tùy ý.

**Lỗi 6 — Tự viết DFS nhưng không ràng buộc semantic.**

Một scanner quét toàn bộ annotation có thể gặp các meta-annotation chuẩn như `@Retention`, `@Target` hoặc nhiều nhánh cấu hình tùy chỉnh. Việc duyệt được không đồng nghĩa biết kết hợp attribute đúng. Hãy xác định bộ annotation được hỗ trợ và quy tắc xung đột rõ ràng.

**Lỗi 7 — Chỉ kiểm tra happy path.**

Với một composed annotation dùng trong dự án thật, nên thử ít nhất: annotation trực tiếp, một tầng meta, nhiều tầng meta, thiếu RUNTIME, class kế thừa, interface, method override, nhiều annotation có cùng meta và trường hợp giá trị mâu thuẫn. Các kịch bản này kiểm tra thiết kế của **bộ xử lý**, chứ không phải chỉ cú pháp annotation.

## 13. Quy tắc thiết kế thực tế

Đối với Java Core, nếu chỉ muốn một **nhãn metadata đơn giản**, một annotation trực tiếp gắn trên class/method thường là đủ. Nếu cần nhóm các cấu hình dưới một tên ngắn, meta-annotation tùy chỉnh làm được phần **mô tả cấu trúc**; phần **diễn giải cấu trúc** cần consumer rõ ràng.

Khi thiết kế annotation tổng hợp, hãy tự trả lời:

- Annotation sẽ được **processor ở compile time** đọc hay **reflection ở runtime** đọc?
- Tầng nào là trực tiếp và tầng nào cần được truy vấn thông qua meta-annotation?
- Có cần kế thừa superclass? Có cần quét interface hoặc method override bằng quy tắc riêng?
- Có nhu cầu đổi/ghi đè attribute của meta-annotation không, hay chỉ cần nhận biết nó có mặt?
- Nếu có nhiều đường dẫn đến cùng meta-annotation, sẽ chọn, gộp hoặc báo lỗi thế nào?

Viết hợp đồng đó thành tài liệu và ví dụ kiểm chứng. Nó giúp tránh kỳ vọng sai về API lõi và làm rõ khác biệt khi chuyển mã giữa Java thuần và framework hỗ trợ annotation tổng hợp.

## 14. Bài tập tự kiểm tra

### Bài 1: Dự đoán getAnnotation

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Checked {}

@Checked
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ValidatedType {}

@ValidatedType
class Customer {}
```

Dự đoán hai biểu thức:

```java
Customer.class.isAnnotationPresent(Checked.class)
ValidatedType.class.isAnnotationPresent(Checked.class)
```

**Đáp án:** `false` và `true`. `Customer` có trực tiếp `@ValidatedType`; `ValidatedType` mới có trực tiếp `@Checked`.

### Bài 2: @Inherited có lan qua interface không?

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Registered {}

@Registered
interface Plugin {}

class FilePlugin implements Plugin {}
```

**Đáp án:** `FilePlugin.class.isAnnotationPresent(Registered.class)` là `false`. Java `@Inherited` không tìm annotation từ interface đã triển khai.

### Bài 3: Annotation có @Retention(RUNTIME) ở tầng trong

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface FeatureFlag {}

@FeatureFlag
@Target(ElementType.TYPE)
@interface Enabled {}

@Enabled
class Example {}
```

Có thể đọc `Enabled` trên `Example.class` bằng reflection runtime thông thường không?

**Đáp án:** không. `Enabled` thiếu `@Retention(RUNTIME)` và mặc định CLASS. `FeatureFlag` có RUNTIME riêng không tự đổi retention của `Enabled`.

### Bài 4: @Repeatable có giúp tìm @FeatureFlag từ @Enabled không?

**Đáp án:** không. `@Repeatable` cùng `getAnnotationsByType(...)` chỉ cung cấp cơ chế chứa/khai triển nhiều annotation cùng loại theo luật Java. Đây không phải API truy vấn tổng quát theo đường đi meta-annotation.

### Bài 5: Một method override có nhận annotation method cha?

**Đáp án:** không tự động theo `@Inherited`. Framework có thể chọn cách duyệt method ở các superclass/interface nhưng Java reflection không tự sao chép hoặc gộp annotation method của class cha vào method override.

### Bài 6: Khi nào viết bộ quét một tầng, khi nào cân nhắc framework?

**Đáp án:** bộ quét một tầng hợp lý khi cần tra một meta-annotation rõ ràng và không phải xử lý hierarchy, alias hay xung đột. Khi cần bắc cầu nhiều tầng, kế thừa phức tạp, thuộc tính thay thế và kết hợp nhiều annotation, hãy thiết kế thuật toán đầy đủ hoặc dùng framework có quy tắc đã được định nghĩa và kiểm thử.

## Tài liệu tham khảo

- [Java SE 17 — `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): định nghĩa các dạng annotation presence và sự khác nhau giữa `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`.
- [Java SE 17 — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): phạm vi superclass, giới hạn interface và ngoài class.
- [JLS Java SE 17 — `9.6 Annotation Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6): meta-annotations chuẩn, `@Inherited`, `@Repeatable`, `@Target`, `@Retention`.
- [Java SE 17 — `java.lang.annotation.Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): retention của từng annotation type.
- [Java SE 17 — `java.lang.annotation.Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html): điều kiện sử dụng annotation trên annotation type, class, method và các khai báo khác.
