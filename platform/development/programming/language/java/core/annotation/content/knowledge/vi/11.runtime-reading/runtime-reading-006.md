# isAnnotationPresent và xử lý khi getAnnotation trả về null trong Java

Khi cần đọc annotation tại runtime, Java reflection cung cấp hai cách thường gặp: **isAnnotationPresent(...)** để kiểm tra một annotation có hiện diện hay không, và **getAnnotation(...)** để lấy đối tượng annotation rồi đọc các phần tử của nó. Nếu không tìm thấy annotation theo quy tắc tra cứu của phần tử được hỏi, **getAnnotation(...) trả về null**.

Đó là một tình huống hợp lệ trong chương trình. Không nên gọi ngay các phương thức trên kết quả mà chưa kiểm tra, vì thao tác đó có thể gây **NullPointerException**. Bài này giải thích khi nào dùng từng API, cách viết nhánh xử lý an toàn, vai trò của **@Retention(RUNTIME)**, điểm khác biệt với truy vấn annotation khai báo trực tiếp và các trường hợp dễ hiểu nhầm như **@Inherited** và **@Repeatable**.

## 1. Hai API được định nghĩa trên AnnotatedElement

Nhiều đối tượng reflection trong Java triển khai **java.lang.reflect.AnnotatedElement**, chẳng hạn **Class**, **Method**, **Field**, **Constructor**, **Parameter** và các đối tượng phản chiếu kiểu phù hợp. Chúng cung cấp những phương thức:

~~~java
boolean isAnnotationPresent(
        Class<? extends java.lang.annotation.Annotation> annotationClass);

<T extends java.lang.annotation.Annotation>
T getAnnotation(Class<T> annotationClass);
~~~

Đây là chữ ký rút gọn của hai phương thức trong API, không phải một chương trình Java độc lập.

- **isAnnotationPresent(A.class)** trả về **true** nếu annotation kiểu A *present* trên phần tử được hỏi; ngược lại là **false**.
- **getAnnotation(A.class)** trả về annotation kiểu A nếu *present*; nếu không thì trả **null**. Đối tượng trả về có các phương thức tương ứng với annotation elements đã khai báo trong A.
- Theo hợp đồng API, **isAnnotationPresent(A.class)** tương đương về kết quả boolean với **getAnnotation(A.class) != null**.
- Nếu đối số **annotationClass** truyền vào là **null**, API có thể ném **NullPointerException**. Đây là lỗi đối số gọi API, khác với trường hợp không tìm thấy annotation và nhận giá trị null.

**Từ khóa present có ý nghĩa quan trọng.** Trên **Class**, nếu annotation type có **@Inherited**, kết quả có thể đến từ superclass; vì vậy present không luôn đồng nghĩa với annotation được viết trực tiếp trên class đang truy vấn.

## 2. Ví dụ tối thiểu: có annotation và không có annotation

Khai báo annotation có khả năng đọc ở runtime:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ComponentInfo {
    String name();
}
~~~

Sử dụng trên một class:

~~~java
@ComponentInfo(name = "billing")
class BillingService {
}

class PlainService {
}
~~~

Với **BillingService**:

~~~java
boolean exists = BillingService.class
        .isAnnotationPresent(ComponentInfo.class);

ComponentInfo info = BillingService.class
        .getAnnotation(ComponentInfo.class);

// exists == true
// info != null
// info.name().equals("billing")
~~~

Với **PlainService**:

~~~java
boolean exists = PlainService.class
        .isAnnotationPresent(ComponentInfo.class);

ComponentInfo info = PlainService.class
        .getAnnotation(ComponentInfo.class);

// exists == false
// info == null
~~~

**Vì sao đây không phải lỗi?** PlainService không có ComponentInfo trong phạm vi tra cứu. Java reflection dùng **null** để biểu thị vắng mặt đối với API **getAnnotation**, còn **isAnnotationPresent** dùng **false**.

### Sai lầm dẫn đến NullPointerException

~~~java
ComponentInfo info = PlainService.class
        .getAnnotation(ComponentInfo.class);

// Sai: info == null, nên gọi name() sẽ ném NPE.
// System.out.println(info.name());
~~~

Lỗi xảy ra khi gọi phương thức **name()** trên tham chiếu null. Lệnh **getAnnotation(...)** tự nó không ném NullPointerException chỉ vì không tìm thấy annotation.

## 3. Khi nào nên dùng isAnnotationPresent?

**Dùng isAnnotationPresent khi chỉ cần biết một dấu hiệu có tồn tại hay không**, đặc biệt phù hợp với marker annotation không có phần tử.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InternalOnly {
}

@InternalOnly
class InternalService {
}

class PublicService {
}
~~~

Kiểm tra:

~~~java
boolean internal = InternalService.class
        .isAnnotationPresent(InternalOnly.class);

boolean external = PublicService.class
        .isAnnotationPresent(InternalOnly.class);

// internal == true
// external == false
~~~

Nếu chương trình cần quyết định có đưa class vào một danh sách hay không, cờ boolean có thể đủ. Dù tên InternalOnly gợi một mục đích, annotation **không tự triển khai bảo mật hoặc chính sách truy cập**. Logic ứng dụng phải thực sự kiểm tra và thực thi quy tắc mong muốn.

Ví dụ một nhánh điều kiện:

~~~java
if (serviceType.isAnnotationPresent(InternalOnly.class)) {
    // Xử lý theo chính sách của ứng dụng.
}
~~~

Biến **serviceType** ở đoạn này được giả định là một đối tượng **Class<?>** đã xác định. Đây là đoạn minh họa ngữ cảnh, không phải một chương trình độc lập.

**Không cần lấy đối tượng annotation** nếu công việc chỉ là nhận biết sự hiện diện của marker.

## 4. Khi cần giá trị annotation, gọi getAnnotation một lần và kiểm tra null

Một mẫu viết rõ ràng và gọn:

~~~java
ComponentInfo info = serviceType.getAnnotation(ComponentInfo.class);

if (info == null) {
    System.out.println("Không có ComponentInfo");
} else {
    System.out.println("name=" + info.name());
}
~~~

Tại đây **serviceType** có kiểu **Class<?>**, và ComponentInfo được định nghĩa như ví dụ trước.

Nếu chỉ dùng giá trị annotation trong nhánh có nó, cũng có thể viết:

~~~java
ComponentInfo info = serviceType.getAnnotation(ComponentInfo.class);
if (info != null) {
    process(info.name());
}
~~~

Lệnh **process(...)** là một phương thức nghiệp vụ do chương trình định nghĩa, không phải API sẵn có của Java. Chỉ sử dụng mẫu trên khi xử lý trường hợp vắng mặt bằng cách bỏ qua là hợp lý.

So sánh hai kiểu:

~~~java
// Hợp lệ nhưng truy vấn hai lần khi cần đọc giá trị.
if (serviceType.isAnnotationPresent(ComponentInfo.class)) {
    ComponentInfo info =
            serviceType.getAnnotation(ComponentInfo.class);
    System.out.println(info.name());
}
~~~

~~~java
// Rõ ràng hơn khi cần đọc annotation.
ComponentInfo info =
        serviceType.getAnnotation(ComponentInfo.class);
if (info != null) {
    System.out.println(info.name());
}
~~~

Cả hai đều hợp lệ nếu cùng phần tử reflection ổn định và annotation tồn tại. **Khi cần dữ liệu**, mẫu thứ hai thường dễ bảo trì hơn vì lấy đối tượng một lần và dùng cùng kết quả để quyết định nhánh. **Khi chỉ cần boolean**, dùng isAnnotationPresent trực tiếp.

Không cần mặc định chọn hai lời gọi để “chắc chắn hơn”. Bản thân **getAnnotation != null** đã cho biết annotation hiện diện theo cùng hợp đồng.

## 5. Ba chính sách xử lý khi getAnnotation trả về null

Cách xử lý đúng phụ thuộc vào yêu cầu nghiệp vụ.

### 5.1. Annotation là tùy chọn: dùng giá trị fallback

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RetryConfig {
    int attempts() default 3;
}
~~~

Mã đọc cấu hình:

~~~java
RetryConfig config =
        serviceType.getAnnotation(RetryConfig.class);

int attempts = config == null ? 1 : config.attempts();
~~~

**Nếu không gắn @RetryConfig**, ứng dụng chọn fallback **1**. **Nếu có @RetryConfig nhưng không điền attempts**, phần tử **attempts()** có default **3**.

Hai tình huống **không giống nhau**:

- **Không có annotation:** **getAnnotation(RetryConfig.class) == null**; ứng dụng tự chọn một giá trị bên ngoài annotation.
- **Có @RetryConfig nhưng bỏ trống attempts:** đối tượng annotation tồn tại; **config.attempts()** trả về default **3** được khai báo trong kiểu annotation.

**Default của annotation element không tạo ra một annotation khi annotation vắng mặt.** Do đó, không suy luận rằng class không có @RetryConfig sẽ tự nhận một đối tượng RetryConfig với attempts = 3.

### 5.2. Annotation là bắt buộc: báo lỗi rõ ràng

Nếu thiết kế yêu cầu class nhất định phải có annotation, có thể từ chối ngay với thông báo cụ thể:

~~~java
ComponentInfo info =
        serviceType.getAnnotation(ComponentInfo.class);

if (info == null) {
    throw new IllegalStateException(
            serviceType.getName() + " thiếu @ComponentInfo");
}

String componentName = info.name();
~~~

Khi thiếu annotation, **IllegalStateException** giúp báo một lỗi cấu hình rõ ràng thay vì để NullPointerException xuất hiện sâu hơn tại chỗ sử dụng **info.name()**. Đây là quyết định của ứng dụng; Java không tự bắt buộc mọi class phải có ComponentInfo.

### 5.3. Annotation là tùy chọn: dùng Optional

Nếu API của ứng dụng muốn biểu diễn rõ “có hoặc không”, có thể chuyển kết quả nullable thành **Optional**:

~~~java
java.util.Optional<ComponentInfo> maybeInfo =
        java.util.Optional.ofNullable(
                serviceType.getAnnotation(ComponentInfo.class));

String componentName =
        maybeInfo.map(ComponentInfo::name).orElse("unclassified");
~~~

**Optional.ofNullable(...)** tạo Optional rỗng khi getAnnotation trả về null. **map(...)** chỉ gọi **name()** khi đối tượng annotation tồn tại; **orElse(...)** cung cấp giá trị thay thế. Cách này hữu ích trong API trả về dữ liệu tùy chọn nhưng không nhất thiết tốt hơn if/else trong mọi đoạn xử lý.

Không dùng **Optional.of(serviceType.getAnnotation(...))** nếu kết quả có thể null: Optional.of không chấp nhận null và sẽ ném NPE.

## 6. Chương trình Java 17+ hoàn chỉnh: boolean, giá trị, fallback và kế thừa

Ví dụ sau là một chương trình độc lập. Nó thể hiện annotation có phần tử, marker annotation và một annotation có **@Inherited** để thấy được sự khác biệt giữa annotation được tra cứu theo lớp cha và annotation khai báo trực tiếp.

Tạo tệp **src/demo/AnnotationLookupDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Feature {
    String name();
    int level() default 1;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Feature(name = "checkout", level = 2)
@Audited
class CheckoutService {
}

@Feature(name = "search")
class SearchService {
}

class LegacyService {
}

@Region("parent")
class ParentService {
}

class ChildService extends ParentService {
}

public class AnnotationLookupDemo {
    public static void main(String[] args) {
        inspect(CheckoutService.class);
        inspect(SearchService.class);
        inspect(LegacyService.class);

        Region inherited =
                ChildService.class.getAnnotation(Region.class);
        Region declared =
                ChildService.class.getDeclaredAnnotation(Region.class);

        System.out.println("Child inherited region="
                + (inherited == null ? "<none>" : inherited.value()));
        System.out.println("Child declared region="
                + (declared == null ? "<none>" : declared.value()));
    }

    private static void inspect(Class<?> type) {
        System.out.println("[" + type.getSimpleName() + "]");

        boolean audited = type.isAnnotationPresent(Audited.class);
        System.out.println("audited=" + audited);

        Feature feature = type.getAnnotation(Feature.class);
        if (feature == null) {
            System.out.println("feature=not configured");
        } else {
            System.out.println("feature=" + feature.name()
                    + ", level=" + feature.level());
        }
    }
}
~~~

Tại thư mục chứa **src**, biên dịch:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationLookupDemo.java
java -cp out demo.AnnotationLookupDemo
~~~

Kết quả stdout:

~~~text
[CheckoutService]
audited=true
feature=checkout, level=2
[SearchService]
audited=false
feature=search, level=1
[LegacyService]
audited=false
feature=not configured
Child inherited region=parent
Child declared region=<none>
~~~

Giải thích:

1. **CheckoutService** có trực tiếp **@Audited** và **@Feature(name = "checkout", level = 2)**, nên marker được phát hiện và hai phần tử Feature được đọc bình thường.
2. **SearchService** không có @Audited nhưng có **@Feature(name = "search")**. Vì **level()** có default là **1**, đoạn code in **level=1**.
3. **LegacyService** không có @Feature. **getAnnotation(Feature.class)** trả null; nhánh if ghi **feature=not configured** và không gọi bất kỳ element nào trên giá trị null.
4. **ChildService** không tự gắn Region nhưng kế thừa từ ParentService. Kiểu Region có **@Inherited**, nên **getAnnotation(Region.class)** trên ChildService tìm được Region từ ParentService, còn **getDeclaredAnnotation(Region.class)** trên chính ChildService trả null.
5. Tất cả ba kiểu annotation đều có **@Retention(RetentionPolicy.RUNTIME)**, nên reflection của Java 17 có thể đọc chúng khi chạy.

Chương trình sử dụng **một public class** là AnnotationLookupDemo trong tệp tương ứng; các annotation/class phụ là top-level package-private nên có thể cùng tồn tại trong tệp. Lệnh java dùng tên đầy đủ **demo.AnnotationLookupDemo** của class chứa main.

**Điều không được suy ra từ kết quả:** Audited không tự kích hoạt hệ thống audit; Feature không tự điều khiển feature flag; Region không tự thay đổi cấu hình. Chương trình hoặc framework phải đọc metadata và thực thi hành vi mong muốn.

## 7. Vì sao getAnnotation có thể null dù bạn nhìn thấy @ trong mã?

Một số nguyên nhân thường gặp cần phân biệt.

### 7.1. Annotation không có retention RUNTIME

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BuildMarker {
}

@BuildMarker
class GeneratedService {
}
~~~

Với reflection runtime tiêu chuẩn:

~~~java
BuildMarker marker =
        GeneratedService.class.getAnnotation(BuildMarker.class);

// marker == null
~~~

**@Retention(CLASS)** yêu cầu metadata được giữ trong class file nhưng không được hiển thị qua Java reflection tại runtime theo cách thông thường. Nếu annotation dùng retention **SOURCE**, metadata không được giữ trong class file sau biên dịch.

Khi không ghi **@Retention**, mặc định là **RetentionPolicy.CLASS**, không phải RUNTIME. Nếu dự định gọi **getAnnotation(...)** lúc chạy, nên khai báo **@Retention(RetentionPolicy.RUNTIME)**.

### 7.2. Bạn đang hỏi sai phần tử reflection

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Endpoint {
}

class Api {
    @Endpoint
    void handle() {
    }
}
~~~

Annotation nằm trên **method handle**, không nằm trên khai báo class Api:

~~~java
boolean onClass =
        Api.class.isAnnotationPresent(Endpoint.class); // false

boolean onMethod =
        Api.class.getDeclaredMethod("handle")
                .isAnnotationPresent(Endpoint.class); // true
~~~

Đoạn trên cần đặt trong một method có khai báo **throws NoSuchMethodException** hoặc xử lý ngoại lệ tương ứng. Khi tìm annotation trên field/parameter/constructor, hãy lấy đúng **Field**, **Parameter** hoặc **Constructor** object thay vì chỉ tra cứu Class.

Với annotation **TYPE_USE**, nó có thể gắn vào vị trí sử dụng kiểu field hoặc kiểu trả về, không phải trực tiếp vào declaration. Khi đó **field.getAnnotatedType().getAnnotation(...)** hoặc **method.getAnnotatedReturnType().getAnnotation(...)** mới là API phù hợp.

### 7.3. Nhầm annotation trực tiếp với annotation kế thừa

Đối với **Class**, **getAnnotation(A.class)** có thể trả annotation từ superclass nếu A có **@Inherited**; trong khi **getDeclaredAnnotation(A.class)** chỉ trả annotation được khai báo trực tiếp trên class đang xét.

Nếu annotation type **không có @Inherited**, class con không tự được tra cứu annotation từ superclass theo cơ chế này. **@Inherited không duyệt interface được implements** và không làm annotation trên method override tự được kế thừa.

Điều này lý giải vì sao code có thể trả false/null dù annotation được nhìn thấy trên interface hay method của một lớp cha; phải kiểm tra chính xác **quan hệ** và **reflection element** được dùng.

### 7.4. Nhầm kiểu annotation hoặc chưa nạp bản class mới

Tên đơn giản giống nhau không chứng minh hai annotation type là cùng một kiểu. Chẳng hạn **com.example.audit.Mark** và **com.example.security.Mark** là hai kiểu khác nhau; yêu cầu **getAnnotation(com.example.security.Mark.class)** không tìm bản của kiểu audit.

Trong môi trường nhiều JAR/class loader, kiểu annotation trên binary đang chạy và kiểu truyền vào reflection cần tương ứng chính xác. Kiểm tra dependency và class thực sự được nạp nếu kết quả không giống kỳ vọng. Sau khi đổi mã nguồn hoặc @Retention, chương trình cũng cần sử dụng đúng binary đã được biên dịch và triển khai.

## 8. Khác biệt giữa getAnnotation, getDeclaredAnnotation và getAnnotationsByType

| API | Kết quả khi không có annotation | Đặc điểm |
| --- | --- | --- |
| **isAnnotationPresent(A.class)** | false | Kiểm tra A có *present* trên phần tử không; tương đương getAnnotation != null |
| **getAnnotation(A.class)** | null | Lấy một annotation A đang hiện diện, có thể tính @Inherited trên Class |
| **getDeclaredAnnotation(A.class)** | null | Chỉ tìm annotation A khai báo trực tiếp, không duyệt kế thừa |
| **getAnnotations()** | Mảng rỗng | Lấy các annotation đang hiện diện |
| **getDeclaredAnnotations()** | Mảng rỗng | Chỉ lấy annotation khai báo trực tiếp |
| **getAnnotationsByType(A.class)** | Mảng A[] rỗng | Hỗ trợ annotation có thể lặp lại và có thể dùng quy tắc kế thừa phù hợp |
| **getDeclaredAnnotationsByType(A.class)** | Mảng A[] rỗng | Hỗ trợ repeatable nhưng chỉ xét annotation trực tiếp/gián tiếp trong chính phần tử |

**Mảng rỗng và null không giống nhau.** Hai API lấy một annotation dùng null để biểu thị vắng mặt; các API trả nhiều annotation dùng **mảng độ dài 0** khi không tìm thấy.

Không nên thay **getAnnotationsByType** bằng **getAnnotation** khi cần đầy đủ các annotation lặp lại của cùng kiểu. Trường hợp này có một khác biệt quan trọng.

### Repeatable annotation: isAnnotationPresent có thể false dù getAnnotationsByType tìm được giá trị

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

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

@Tag("fast")
@Tag("safe")
class Processor {
}
~~~

Khi biên dịch hai annotation Tag cùng loại ở trên một class, thông tin có thể được biểu diễn qua annotation container **Tags**. Vì vậy:

~~~java
boolean singlePresent =
        Processor.class.isAnnotationPresent(Tag.class);

Tag one = Processor.class.getAnnotation(Tag.class);
Tag[] all = Processor.class.getAnnotationsByType(Tag.class);

// singlePresent == false
// one == null
// all.length == 2
// all[0].value().equals("fast")
// all[1].value().equals("safe")
~~~

Đây là hành vi chuẩn đối với trường hợp **hai @Tag lặp trực tiếp** nêu trên: Tag được chứa gián tiếp trong Tags; **getAnnotation(Tag.class)** và **isAnnotationPresent(Tag.class)** không tự mở container. Khi người dùng cần lấy cả hai Tag, dùng **getAnnotationsByType(Tag.class)**.

Quy tắc về **repeatable annotations** có các trường hợp trực tiếp/gián tiếp và kế thừa riêng; cách an toàn là chọn API **ByType** khi yêu cầu của bạn thực sự là “mọi annotation thuộc kiểu A” thay vì “một annotation A đang present”.

## 9. Có nên luôn gọi isAnnotationPresent trước getAnnotation?

Không cần trong trường hợp chỉ muốn đọc phần tử của annotation. Hai lời gọi có thể làm lặp việc truy vấn metadata, đồng thời làm mã dài thêm mà không tăng độ rõ ràng:

~~~java
// Dùng khi chỉ cần boolean.
boolean marked = type.isAnnotationPresent(Audited.class);

// Dùng khi cần đọc element và xử lý vắng mặt.
Feature feature = type.getAnnotation(Feature.class);
if (feature != null) {
    useFeature(feature.name(), feature.level());
}
~~~

**useFeature(...)** trong ví dụ là một phương thức nghiệp vụ giả định.

Với logic dựa trên giá trị, nguyên tắc thực tế là **lấy annotation một lần, kiểm tra null, rồi đọc các element khi đã chắc chắn có đối tượng**. Trường hợp rất cần kiểm tra boolean độc lập, isAnnotationPresent là lựa chọn tường minh.

Nếu bắt buộc phải có annotation thì thay vì im lặng bỏ qua, trả một lỗi cấu hình rõ ràng. Nếu tùy chọn, dùng fallback hợp lý hoặc Optional. Việc chọn fallback hay lỗi phụ thuộc hợp đồng nghiệp vụ; không có một cách áp dụng cho tất cả.

## 10. Phân biệt null của getAnnotation và giá trị phần tử annotation

Một annotation element bình thường không thể khai báo **null** làm giá trị:

~~~java
@interface Label {
    String value() default "unknown";
}

// Sai: annotation element value không được là null.
// @Label(null)
// class Invalid {}
~~~

Với **@Label("ok")**, **getAnnotation(Label.class)** trả về đối tượng Label và **value()** trả về **"ok"**. Với **@Label** không truyền value, đối tượng Label tồn tại và **value()** trả về **"unknown"**.

Với một class **không có @Label**, **getAnnotation(Label.class)** trả về **null** (nếu không có cơ chế hiện diện khác như kế thừa). Đó là **sự vắng mặt của chính annotation**, không phải “Label.value() là null”.

Một số ngoại lệ khi xử lý binary annotation không còn tương thích có thể phát sinh lúc truy cập element, chẳng hạn **IncompleteAnnotationException** nếu một element bắt buộc không có giá trị trong metadata cũ và không có default trong kiểu mới. Đây là vấn đề tương thích binary/runtime khác với null thông thường khi annotation vắng mặt. Đừng dùng null check để khẳng định mọi thao tác đọc annotation sẽ không bao giờ có ngoại lệ.

## 11. Các lỗi phổ biến

| Lỗi hoặc nhận định | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi **getAnnotation(...).value()** trực tiếp | getAnnotation có thể trả null | Lấy biến trước, kiểm tra null rồi mới gọi element |
| Dùng **Optional.of(getAnnotation(...))** | Optional.of không nhận null | Dùng **Optional.ofNullable(...)** |
| Gọi isAnnotationPresent rồi vẫn quên xử lý kết quả | Boolean không tự bảo vệ thao tác sau | Đặt logic trong nhánh if hoặc kiểm tra kết quả getAnnotation |
| Cho rằng element có default nên getAnnotation không thể null | Default chỉ áp dụng nếu annotation hiện diện | Phân biệt thiếu annotation và thiếu element-value |
| Bỏ @Retention hoặc để CLASS mà muốn runtime reflection đọc thấy | Retention mặc định là CLASS | Thêm **@Retention(RUNTIME)** cho annotation runtime |
| Tìm annotation method bằng **SomeClass.class.getAnnotation(...)** | Đang truy vấn class, không phải method | Lấy **Method** qua reflection rồi truy vấn |
| Dùng getDeclaredAnnotation để lấy annotation từ superclass | Declared chỉ xét trực tiếp | Dùng getAnnotation khi cần quy tắc @Inherited |
| Cho rằng @Inherited tìm annotation trên implements interface | @Inherited không duyệt interface | Duyệt interface riêng nếu nghiệp vụ yêu cầu |
| Dùng getAnnotation để lấy tất cả @Tag lặp lại | Có thể chỉ có container annotation hiện diện | Dùng **getAnnotationsByType(Tag.class)** |
| Nhầm **getAnnotations()** không có dữ liệu với null | API trả về mảng, không dùng null cho trường hợp rỗng | Kiểm tra **array.length == 0** |
| Truyền **null** thay cho annotationClass | Đây là đối số không hợp lệ | Truyền đúng class literal annotation, ví dụ Feature.class |

## 12. Bài tập tự kiểm tra

**Bài 1.** Một class không có **@Feature**. Kết quả của hai lời gọi sau là gì?

~~~java
boolean present = SomeClass.class.isAnnotationPresent(Feature.class);
Feature feature = SomeClass.class.getAnnotation(Feature.class);
~~~

Giả sử không có annotation kế thừa phù hợp và Feature có runtime retention: **present = false**, **feature = null**. Gọi **feature.name()** sau đó sẽ gây NPE.

**Bài 2.** Kiểu **@RetryConfig** có **attempts() default 3**. Một class không có **@RetryConfig** có tự trả về đối tượng RetryConfig với attempts = 3 không? **Không.** Annotation vẫn vắng mặt; chỉ khi annotation được gắn mà phần tử attempts bị bỏ trống, default 3 mới được sử dụng.

**Bài 3.** Nếu một thư viện cần đọc giá trị **Feature.name()** khi có annotation, dùng mẫu nào phù hợp hơn: kiểm tra isAnnotationPresent rồi gọi getAnnotation, hay chỉ gọi getAnnotation và kiểm tra null? **Chỉ gọi getAnnotation một lần rồi kiểm tra null** thường rõ và ngắn hơn.

**Bài 4.** Tại sao **ChildService.class.getAnnotation(Region.class)** tìm thấy Region nhưng **getDeclaredAnnotation** không thấy? **Region có @Inherited**, được khai báo trên superclass; bản thân ChildService không tự khai báo.

**Bài 5.** Hai **@Tag** cùng loại được gắn trên một class thông qua **@Repeatable**. Vì sao **getAnnotationsByType(Tag.class).length** có thể là 2 trong khi **isAnnotationPresent(Tag.class)** là false? **ByType** mở container annotation, còn isAnnotationPresent chỉ theo sự hiện diện của annotation kiểu Tag như getAnnotation.

## 13. Tài liệu Java chính thức

- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — hợp đồng isAnnotationPresent, getAnnotation, getDeclaredAnnotation và getAnnotationsByType.
- **Java SE 17 — Class:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — các phương thức reflection trên class.
- **Java SE 17 — RetentionPolicy:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html — SOURCE, CLASS và RUNTIME.
- **Java Language Specification §9.6.4.3 — @Inherited:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3 — cơ chế tìm annotation trên superclass.
- **Java Language Specification §9.6.3 — Repeatable Annotation Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3 — quy tắc annotation lặp lại và container.

Khi chỉ muốn biết annotation có hiện diện, chọn **isAnnotationPresent**. Khi cần đọc giá trị, chọn **getAnnotation**, kiểm tra **null** và xử lý theo hợp đồng nghiệp vụ. Trước khi kết luận annotation bị thiếu, hãy xác nhận **retention**, **đối tượng reflection**, **quan hệ kế thừa** và **việc annotation có được dùng theo kiểu repeatable hay không**.
