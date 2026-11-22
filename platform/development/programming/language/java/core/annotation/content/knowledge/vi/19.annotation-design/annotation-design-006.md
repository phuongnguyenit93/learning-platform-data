# Phân biệt meta-annotation Java Core với annotation tổng hợp của framework

**Meta-annotation** là annotation được đặt **trên khai báo một kiểu annotation khác**. Java Core đã có nhiều meta-annotation chuẩn như `@Target`, `@Retention`, `@Documented`, `@Inherited` và `@Repeatable`, nhằm quy định một số **quy tắc ngôn ngữ, compiler và Reflection**. Trong khi đó, một **composed annotation** (*annotation tổng hợp*) của framework, chẳng hạn Spring, dùng chính cú pháp meta-annotation ấy để **kết hợp ý nghĩa nghiệp vụ và cấu hình**, đồng thời dựa vào **thuật toán dò tìm/gộp metadata do framework cung cấp**.

**Điểm cốt lõi:** cú pháp Java cho phép annotation nằm trên một annotation khác, nhưng **Java Reflection chuẩn không tự suy ra rằng mọi meta-annotation trở thành annotation trực tiếp trên class mang annotation tổng hợp**. Một framework muốn hỗ trợ hành vi như vậy phải cung cấp logic tìm kiếm, hợp nhất thuộc tính và xử lý quy tắc riêng.

Bài học thuộc chủ đề **thiết kế annotation trong Java Core**. Ta sẽ bắt đầu với hợp đồng của Java, kiểm tra bằng chương trình Java 17 không dùng thư viện ngoài, rồi so sánh với trường hợp Spring để thấy **ranh giới trách nhiệm** rõ ràng.

## 1. “Meta-annotation” là một vị trí cú pháp, không phải một chức năng duy nhất

Java dùng ký hiệu `@` cho cả annotation thông thường và meta-annotation. Khác biệt phụ thuộc **đối tượng được gắn annotation**:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {
}

@Audited
class InvoiceService {
}
```

Trong đoạn này:

- `@Retention` và `@Target` được đặt trên `@interface Audited`: chúng là **meta-annotation**, mô tả quy tắc sử dụng `Audited`.
- `@Audited` nằm trên `class InvoiceService`: đây là một **lần áp dụng annotation lên class**.
- Cả hai cách viết đều tuân thủ cú pháp annotation của ngôn ngữ Java.

Không phải annotation nào nằm trên một annotation khác cũng thuộc bộ meta-annotation chuẩn của Java. Một annotation nghiệp vụ được khai báo với `@Target(ANNOTATION_TYPE)` cũng có thể dùng làm **meta-annotation tùy biến**; điều đó **không tự làm nó có ý nghĩa cho Reflection trên class ở tầng dưới**.

Ví dụ `@RequiredRole("ADMIN")` có thể được đặt trên `@AdminOnly`. Java biết cấu trúc:

```text
Khai báo @interface AdminOnly
    └─ được annotate bởi @RequiredRole("ADMIN")

Khai báo class ReportPage
    └─ được annotate bởi @AdminOnly
```

Nhưng Reflection trực tiếp trên `ReportPage` **không được yêu cầu** tự “đi xuyên” `@AdminOnly` rồi trả `@RequiredRole`. Muốn dùng mối liên hệ đó, code ứng dụng hoặc framework phải **truy cập annotation type `AdminOnly` và phân tích tiếp**.

## 2. Năm meta-annotation tiêu biểu do Java Core định nghĩa

Các annotation chuẩn dưới đây thuộc `java.lang.annotation` và có ý nghĩa được Java quy định.

| Meta-annotation | Ý nghĩa cốt lõi của Java | Điều nó **không** làm |
| --- | --- | --- |
| `@Target` | Chỉ định những **vị trí cú pháp** cho phép sử dụng annotation type. | Không cho phép framework tự động xử lý các annotation nằm ở vị trí đó. |
| `@Retention` | Quy định annotation còn tồn tại đến mức **SOURCE**, **CLASS**, hay **RUNTIME**. | Không tự gộp các annotation từ nhiều tầng. |
| `@Documented` | Đánh dấu annotation là thành phần của API công khai, để công cụ sinh tài liệu chuẩn như Javadoc hiển thị khi phù hợp. | Không khiến mọi annotation lồng/meta khác tự xuất hiện như annotation trực tiếp. |
| `@Inherited` | Cho phép một annotation type được Reflection tìm qua **chuỗi superclass** của class, trong những trường hợp quy định. | Không tìm trong interface được implements; không tạo cơ chế composed-annotation tổng quát. |
| `@Repeatable` | Cho phép nhiều lần dùng **cùng một annotation type** tại cùng một vị trí thông qua một **container** hợp lệ. | Không có nghĩa những annotation **khác loại** sẽ được tổng hợp hay hợp nhất thuộc tính. |

Cú pháp ví dụ:

```java
import java.lang.annotation.*;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface FeatureFlag {
    String value() default "on";
}
```

Với kiểu `FeatureFlag`:

- Compiler kiểm tra việc dùng trên các **kiểu** vì `@Target(TYPE)`.
- Reflection runtime có thể đọc nó vì `@Retention(RUNTIME)`.
- Javadoc có thể thể hiện annotation theo quy tắc `@Documented`.
- `@Inherited` chỉ tác động đến một số truy vấn trên **class con** khi annotation được đặt lên **class cha**.
- Không có yếu tố nào ở đây khiến `@FeatureFlag` trở thành quy tắc bật feature tự động trong ứng dụng. **Business logic phải đọc và diễn giải** `FeatureFlag`.

**`@Target(ANNOTATION_TYPE)`** là cách khai báo một annotation dành riêng cho việc **đánh dấu khai báo annotation type**. Khi muốn một annotation vừa dùng trực tiếp trên class, vừa dùng để đánh dấu annotation khác, ta có thể dùng `@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})` cho phép cả hai mục đích.

### Ba mức của `@Retention`

```java
@Retention(RetentionPolicy.SOURCE)   // Dùng trong source, không được giữ trong class file
@Retention(RetentionPolicy.CLASS)    // Giữ trong class file, Reflection thông thường không thấy
@Retention(RetentionPolicy.RUNTIME)  // Giữ để Reflection runtime đọc được
```

Ba dòng là **minh họa cú pháp lựa chọn**, không đặt cả ba trên cùng một annotation type.

Nếu **không khai báo `@Retention`**, mặc định là `RetentionPolicy.CLASS`. Khi một framework dùng Reflection để tìm annotation runtime, một annotation có retention `CLASS` thường sẽ **không được tìm thấy**, dù cú pháp meta-annotation và cấu hình logic có vẻ đúng.

## 3. Meta-annotation của Java Core có ngữ nghĩa đặc biệt vì ngôn ngữ định nghĩa

Tại sao Java biết cách xử lý `@Retention` hoặc `@Target`, còn không tự động hiểu `@RequiredRole`? Vì Java Language Specification và các Java SE API đã **định nghĩa trước ý nghĩa** của các annotation chuẩn. Compiler và Reflection chỉ phải tuân thủ những hợp đồng đó.

Ví dụ:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface OnlyOnMethod {
}

// @OnlyOnMethod class WrongPlace {} // Lỗi biên dịch: target METHOD, không phải TYPE
```

Điểm kiểm tra vị trí là trách nhiệm **của trình biên dịch Java**, không cần một framework quét code.

Tương tự:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Marker {
}

@Marker
class Parent {
}

class Child extends Parent {
}
```

Với `Child.class.getAnnotation(Marker.class)`, Java Reflection có thể tìm `Marker` theo **quy tắc kế thừa annotation trên class**. Điều này khác hoàn toàn với “tìm một annotation tùy ý đặt trên annotation type khác”.

**Hạn chế của `@Inherited` cần nhớ:**

1. Truy vấn **class** và đi qua **superclass**, không tự tìm metadata trên interface được implements.
2. Không làm method/field/parameter tự kế thừa annotation theo ý nghĩa tổng quát.
3. `Class.getDeclaredAnnotation(Marker.class)` chỉ tìm annotation **khai báo trực tiếp**, nên class con không khai báo `@Marker` có thể trả `null` với API này.
4. Việc `Marker` được gắn `@Inherited` không khiến mọi **meta-annotation nằm trên `Marker`** tự truyền xuống class con.

Framework có thể có quy tắc tìm kiếm xuyên class hierarchy và interface phong phú hơn; không nên nhầm chúng với hợp đồng `@Inherited` của Java.

## 4. Annotation tổng hợp của framework khác ở đâu?

**Composed annotation** là cách dùng **một annotation tùy biến** để đại diện cho **một tập metadata hoặc nhiều annotation khác**, dựa trên **bộ xử lý của một framework cụ thể**.

Trong hệ sinh thái Spring, một ví dụ quen thuộc:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.lang.annotation.*;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Service
@Transactional
public @interface TransactionalService {
}
```

Đây là **đoạn ví dụ phụ thuộc Spring**, không phải mã chỉ với JDK; cần các dependency Spring tương ứng và một annotation file có tên đúng để biên dịch.

Một class dùng:

```java
@TransactionalService
class PaymentService {
}
```

Spring có cơ chế xử lý annotation **qua nhiều tầng meta-annotation** để nhận diện stereotype `@Service` và metadata giao dịch `@Transactional` khi những cơ chế tương ứng được cấu hình. Nhờ đó, tác giả code giảm việc lặp nhiều annotation trên các class.

Nhưng **Java Core đơn thuần** không tự động bảo đảm các hành vi sau:

- `Class.getAnnotation(Service.class)` trên `PaymentService` sẽ không tự tìm `@Service` gián tiếp qua `@TransactionalService`.
- `Class.getAnnotation(Transactional.class)` trên `PaymentService` cũng không tự lấy `@Transactional` chỉ nhờ Java Reflection chuẩn.
- Việc chỉ viết `@TransactionalService` **không tự bật transaction management** nếu ứng dụng chưa có các thành phần/configuration cần thiết của Spring.
- Spring xử lý stereotype, transaction và attribute alias dựa trên **quy tắc riêng của nó**, không phải vì Java có một toán tử annotation tổng hợp được compiler hiểu.

Về mặt ngôn ngữ, `@TransactionalService` là một annotation type có **meta-annotation thông thường**; “tổng hợp” là **ngữ nghĩa của tầng xử lý**.

## 5. Ví dụ Java 17 hoàn chỉnh: Java Reflection có và không thấy gì?

Ví dụ này dùng **duy nhất Java SE 17**. Nó kiểm tra ba điều:

1. Class gắn trực tiếp một annotation sẽ được Reflection đọc như annotation trực tiếp.
2. Một annotation **nằm trên annotation type khác** không tự xuất hiện như annotation của class dùng kiểu trung gian đó.
3. `@Inherited` có tác dụng khác: tìm trên superclass trong những trường hợp được Java quy định, nhưng không tìm trên interface.

Tạo file **`CoreMetaVsComposedDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@interface RequiredRole {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@RequiredRole("ADMIN")
@interface AdminOnly {
}

@AdminOnly
class AdminPage {
}

@RequiredRole("ADMIN")
class DirectPage {
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tracked {
}

@Tracked
class BaseReport {
}

class MonthlyReport extends BaseReport {
}

@Tracked
interface TaggedInterface {
}

class InterfaceImplementation implements TaggedInterface {
}

public class CoreMetaVsComposedDemo {
    public static void main(String[] args) {
        System.out.println("direct=" +
                DirectPage.class.isAnnotationPresent(RequiredRole.class));

        System.out.println("metaIsNotDirect=" +
                (AdminPage.class.getAnnotation(RequiredRole.class) == null));

        System.out.println("composedPresent=" +
                AdminPage.class.isAnnotationPresent(AdminOnly.class));

        RequiredRole meta = AdminOnly.class.getAnnotation(RequiredRole.class);
        System.out.println("metaOnAnnotationType=" + meta.value());

        AdminOnly present = AdminPage.class.getAnnotation(AdminOnly.class);
        RequiredRole manual = present.annotationType()
                .getAnnotation(RequiredRole.class);
        System.out.println("manualTraverse=" + manual.value());

        System.out.println("inheritedFromSuperclass=" +
                MonthlyReport.class.isAnnotationPresent(Tracked.class));

        System.out.println("notDeclaredOnSubclass=" +
                (MonthlyReport.class.getDeclaredAnnotation(Tracked.class) == null));

        System.out.println("notInheritedFromInterface=" +
                !InterfaceImplementation.class.isAnnotationPresent(Tracked.class));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CoreMetaVsComposedDemo.java
java CoreMetaVsComposedDemo
```

**Stdout:**

```text
direct=true
metaIsNotDirect=true
composedPresent=true
metaOnAnnotationType=ADMIN
manualTraverse=ADMIN
inheritedFromSuperclass=true
notDeclaredOnSubclass=true
notInheritedFromInterface=true
```

### Phân tích kết quả

- **`direct=true`**: `DirectPage` có chính `@RequiredRole("ADMIN")` trên khai báo class.
- **`metaIsNotDirect=true`**: `AdminPage` chỉ có `@AdminOnly`. Java Reflection truy vấn `RequiredRole` **trên `AdminPage`** không tự đi xuyên `AdminOnly` để lấy `RequiredRole`.
- **`composedPresent=true`**: `AdminOnly` thật sự được gắn trực tiếp lên `AdminPage`.
- **`metaOnAnnotationType=ADMIN`**: `RequiredRole` **có mặt trên khai báo `@interface AdminOnly`**, nên truy cập `AdminOnly.class.getAnnotation(RequiredRole.class)` đọc được.
- **`manualTraverse=ADMIN`**: code lấy `@AdminOnly` trên `AdminPage`, hỏi `annotationType()` rồi đọc meta-annotation ở **annotation type** đó. Đây là một bước **duyệt thủ công**, không phải Java đã hợp nhất annotation lên `AdminPage`.
- **`inheritedFromSuperclass=true`**: với `@Tracked` đã gắn `@Inherited`, truy vấn trên `MonthlyReport` có thể lấy annotation từ `BaseReport`.
- **`notDeclaredOnSubclass=true`**: class con không khai báo trực tiếp `@Tracked`; `getDeclaredAnnotation` vẫn trả `null`.
- **`notInheritedFromInterface=true`**: Java không lấy `@Tracked` trên interface `TaggedInterface` cho class `InterfaceImplementation` thông qua `@Inherited`.

**Lưu ý:** cách duyệt thủ công trong ví dụ chỉ xử lý **một tầng** meta-annotation. Nếu annotation được tổng hợp qua nhiều tầng, có vòng tham chiếu, nhiều annotation trùng loại, thuộc tính cần override hoặc class hierarchy phức tạp, phải thiết kế thuật toán riêng. Đó chính là lý do các framework có thư viện xử lý annotation thay vì yêu cầu mọi ứng dụng tự đi sâu.

## 6. Java Reflection không đồng nghĩa “không thể đọc meta-annotation”

Một phát biểu như “Java không hỗ trợ meta-annotation tùy biến” là **sai**. Java cho phép đặt annotation lên annotation type nếu target hợp lệ, lưu chúng theo retention, và đọc metadata của chính annotation type khi runtime.

Vấn đề cần phân biệt là **API nhìn từ vị trí nào và có tự đi nhiều tầng không**:

```java
AdminPage.class.getAnnotation(RequiredRole.class);  // null
AdminPage.class.getAnnotation(AdminOnly.class);      // có annotation AdminOnly
AdminOnly.class.getAnnotation(RequiredRole.class);   // có annotation RequiredRole
```

Cả ba lệnh trên đều là Java Reflection chuẩn và đều hoạt động theo đúng hợp đồng. Phần Java **không mặc định làm hộ** là chuyển dòng thứ nhất thành một câu trả lời dựa trên đường `AdminPage → AdminOnly → RequiredRole`.

Một thư viện có thể tự xây thuật toán: lấy annotation trực tiếp, đọc `annotationType()`, duyệt các meta-annotation theo từng tầng và trả metadata tìm thấy. Nhưng cần quyết định ít nhất:

- Có duyệt **bao nhiêu tầng** và xử lý **chu trình** thế nào?
- Nếu hai nhánh chứa cùng annotation type với giá trị khác nhau, **ưu tiên nhánh nào**?
- Có cho phép annotation ở superclass, interface hoặc method bị override tham gia tìm kiếm không?
- Có hỗ trợ `@Repeatable` và container không?
- Có hợp nhất giá trị mặc định, thuộc tính cùng tên và **alias** không?
- Metadata nguồn/đích dùng retention nào và có sẵn lúc runtime không?

**Java SE không định nghĩa một câu trả lời tổng quát** cho những câu hỏi composition này. Spring và các framework khác có các chiến lược riêng.

## 7. `@Target` và `@Retention` phải thiết kế cho từng tầng

Giả sử bạn muốn khai báo `@AdminOnly` để đặt trên class, với marker bên trong có ý nghĩa `@RequiredRole`.

Cấu hình đúng tối thiểu cho việc đọc bằng Reflection runtime:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@interface RequiredRole {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@RequiredRole("ADMIN")
@interface AdminOnly {
}
```

**Hai annotation có metadata của chính chúng**, không tự sao chép:

- `RequiredRole` cần `@Target(ANNOTATION_TYPE)` (có thể kết hợp target khác) để áp dụng được trên khai báo `@interface AdminOnly`.
- `AdminOnly` cần `@Target(TYPE)` để người dùng đặt nó trên class.
- Nếu cần Reflection lúc chạy, `RequiredRole` cần retention `RUNTIME` để đọc từ `AdminOnly.class`.
- `AdminOnly` cũng cần retention `RUNTIME` để đọc từ `AdminPage.class`.
- Gắn `@Retention(RUNTIME)` cho `RequiredRole` **không tự động** làm `AdminOnly` có retention runtime; từng annotation type tuân theo `@Retention` của chính nó.

Một lỗi thường gặp là chỉ đặt `@Retention(RUNTIME)` lên annotation nằm **bên trong**, còn annotation tổng hợp bên ngoài không khai báo gì và mặc định `CLASS`. Khi đó việc đọc `@AdminOnly` từ class bằng Reflection không thực hiện được như ví dụ.

Tương tự, chỉ đặt `@Target(ANNOTATION_TYPE)` lên marker bên trong không khiến `@AdminOnly` tự dùng được trên method/field; target của `AdminOnly` phải phù hợp với nơi sử dụng thực tế.

## 8. Đừng nhầm `@Inherited` với cơ chế composition của framework

`@Inherited` là **một meta-annotation chuẩn của Java**, nhưng ngữ nghĩa của nó rất **hẹp**. Đặt `@Inherited` lên `@RequiredRole` không có nghĩa là Java sẽ tự biến mọi class dùng `@AdminOnly` thành class trực tiếp mang `@RequiredRole`.

Ví dụ phân biệt:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Region("east")
class BaseController {
}

class ChildController extends BaseController {
}
```

Đây là **đoạn minh họa** độc lập. `ChildController.class.getAnnotation(Region.class)` có thể tìm được annotation từ `BaseController`, còn `getDeclaredAnnotation(Region.class)` trên `ChildController` trả `null`. Nhưng nếu `@Region` chỉ là meta-annotation trên `@SpecialController` và class con được gắn `@SpecialController`, Java không tự “giải nén” `Region` từ annotation trung gian nhờ `@Inherited`.

Điểm dễ nhầm nữa: interface không nằm trong đường tìm của `@Inherited` chuẩn. Một số framework cho phép tìm annotation ở **interface** hoặc ở method theo interface/override; đó là **quy tắc framework**, không được suy ra từ `@Inherited`.

## 9. `@Repeatable` cũng không phải annotation tổng hợp kiểu framework

`@Repeatable` là cơ chế ngôn ngữ dành cho **nhiều lần áp dụng một annotation type** tại cùng vị trí. Java cần một annotation chứa (container) có phần tử `value()` kiểu mảng của annotation đó:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}

@Tag("audit")
@Tag("monitor")
class LogService {
}
```

Đây là một ví dụ minh họa độc lập, không có `main`. `@Repeatable` cho phép hai `@Tag` trên một class. Compiler áp dụng **quy tắc container** theo Java; Reflection có API như `getAnnotationsByType(Tag.class)` để đọc các annotation lặp.

Nó khác composed annotation ở chỗ:

- `@Repeatable(Tags.class)` liên kết **một annotation type với container cùng kiểu phần tử**.
- `@AdminOnly` tổng hợp `@RequiredRole`, `@Service` hay `@Transactional` là việc kết hợp **những loại annotation khác nhau**, cùng ngữ nghĩa áp dụng do thư viện/framework diễn giải.
- `getAnnotationsByType(...)` của Java có quy tắc nhìn qua **repeatable container**, nhưng **không biến nó thành bộ tìm kiếm mọi meta-annotation tùy biến**.

Nếu dùng annotation lặp ở runtime, nhớ thiết kế `@Retention(RUNTIME)` cho cả annotation lặp và container nếu cần Reflection; cặp khai báo phải tuân thủ quy tắc tương thích retention/target theo Java Language Specification.

## 10. Spring xử lý annotation tổng hợp như thế nào?

Trong Spring, một số annotation có ý nghĩa **stereotype** hoặc **cấu hình**:

- `@Component` nhận diện một kiểu là ứng viên cho component scanning của Spring; `@Service` và `@Repository` có meta-annotation gắn `@Component`.
- `@RestController` kết hợp ý nghĩa của `@Controller` và `@ResponseBody` trong Spring Web.
- `@GetMapping` về mặt thiết kế là specialization của `@RequestMapping` với HTTP method GET và có cơ chế alias cho nhiều thuộc tính như `path`/`value`.
- Annotation tùy biến như `@TransactionalService` có thể đặt `@Service` và `@Transactional` làm meta-annotation để framework giải thích.

Spring có các API xử lý metadata được tổ chức chuyên biệt, ví dụ `org.springframework.core.annotation.AnnotatedElementUtils` và `org.springframework.core.annotation.MergedAnnotations`.

Một ví dụ **phụ thuộc Spring**, tách khỏi chương trình Java 17 độc lập ở mục 5:

```java
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.stereotype.Service;

Service service = AnnotatedElementUtils.findMergedAnnotation(
        PaymentService.class,
        Service.class
);
```

Đây là **snippet**: muốn biên dịch cần Spring dependency, một `PaymentService` được annotate phù hợp, và đặt code trong class/method. Spring có thể tìm `@Service` từ một cấu trúc meta-annotation phù hợp **theo thuật toán của Spring**, trong khi `PaymentService.class.getAnnotation(Service.class)` là Reflection chuẩn không tự tìm qua composed annotation.

Không nên hiểu rằng **mọi** framework cũng tìm và merge giống Spring, hoặc mọi API trong Spring có cùng chiến lược. Các lựa chọn như direct, inherited, meta-present, type hierarchy, method hierarchy, repeatable và attribute resolution còn phụ thuộc API và phiên bản framework.

### Thuộc tính được gộp và alias

Trong Java Core, hai phương thức element của hai annotation **không tự có liên hệ** chỉ vì trùng tên. Ví dụ `@A(name="x")` và `@B(name="x")` là hai giá trị riêng.

Spring định nghĩa thêm annotation `@AliasFor` và các quy tắc **alias/override** khi xử lý merged annotations. Một ví dụ **Spring-specific**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface NamedComponent {
    @AliasFor(annotation = Component.class, attribute = "value")
    String value() default "";
}
```

Đoạn trên phải nằm trong file **`NamedComponent.java`** và cần Spring trên compile classpath; nó không phải cú pháp Java thuần có thể dùng nếu chưa thêm thư viện. Khi một thành phần Spring thích hợp xử lý `@NamedComponent("billing")`, quy tắc alias có thể ánh xạ giá trị qua thuộc tính `Component.value` trong mô hình merged annotation của Spring.

**`@AliasFor` không phải meta-annotation tiêu chuẩn của Java.** `javac` chỉ nhìn thấy một annotation được khai báo hợp lệ; chính Spring định nghĩa cách diễn giải quan hệ alias và các ràng buộc tương ứng. Không thể tạo `@AliasFor` rồi hy vọng `Class.getAnnotation(Component.class)` của Java Core tự trả về metadata đã gộp.

## 11. Bảng so sánh toàn diện

| Khía cạnh | Meta-annotation Java Core | Composed annotation của framework |
| --- | --- | --- |
| Ai định nghĩa ngữ nghĩa? | Java Language Specification và Java SE API cho các meta-annotation chuẩn. | Framework hoặc thư viện xử lý annotation. |
| Cú pháp? | `@Retention`, `@Target`, v.v. trên `@interface`. | Cũng là cú pháp annotation Java đặt trên `@interface`. |
| Mục tiêu phổ biến | Vị trí hợp lệ, retention, tài liệu, kế thừa ở class, lặp qua container. | Gom stereotype, cấu hình, policy, route hoặc hành vi của nhiều annotation. |
| Có cần dependency ngoài JDK không? | Không với `java.lang.annotation`. | Có nếu dùng Spring/Jakarta/thư viện cụ thể. |
| Compiler tự hiểu ngữ nghĩa không? | Với quy tắc tiêu chuẩn như `@Target`, `@Repeatable`: có. | Compiler thường chỉ kiểm tra cú pháp/kiểu; hành vi composition do framework. |
| Reflection chuẩn tìm meta-annotation trên annotation type được không? | Có, nếu retention cho phép. | Có thể đọc thông tin cấu trúc; nhưng không mặc định merge lên class được annotate. |
| Tự động tìm xuyên nhiều tầng annotation tùy biến? | Không có cơ chế tổng quát trong `Class.getAnnotation(...)`. | Có thể có, theo API/thuật toán của framework. |
| Gộp/ghi đè thuộc tính và alias? | Không có nguyên tắc alias giữa các annotation khác loại. | Có thể có, như Spring `@AliasFor`/`MergedAnnotations`. |
| Ảnh hưởng kế thừa? | `@Inherited` có quy tắc hẹp chỉ trên chuỗi superclass của class. | Có thể bổ sung tìm trong hierarchy/interface/method tùy API. |
| Thời điểm xử lý? | Compiler, Javadoc, annotation processing và Reflection theo từng annotation type. | Framework thường đọc metadata khi bootstrap/runtime; cũng có thư viện xử lý khi build. |

Hai cột **không đối lập tuyệt đối**. Framework vẫn dựa trên annotation hợp lệ của Java Core, và một dự án Java Core thuần vẫn có thể **tự viết một resolver** duyệt meta-annotation. Điều phân biệt là **nguồn gốc của ngữ nghĩa tự động**: Java chuẩn hay logic được framework/thư viện bổ sung.

## 12. Thiết kế annotation tránh phụ thuộc ngầm vào framework

Khi thiết kế một annotation, hãy xác định **người tiêu thụ metadata** là ai trước:

### Trường hợp A: annotation được Java compiler hoặc annotation processor xử lý

Ví dụ một marker chỉ dùng lúc build để generator đọc:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateMapper {
}
```

Processor có thể duyệt `RoundEnvironment`, `Element`, `AnnotationMirror` để đọc `@GenerateMapper`; không nhất thiết phải có retention `RUNTIME`.

Nếu tự thiết kế meta-annotation trên các annotation tùy biến để processor nhận diện, processor **phải tự duyệt** từ annotation đang dùng đến annotation type được meta-annotate. `@SupportedAnnotationTypes(...)` không có nghĩa mọi annotation meta-present sẽ được compiler tự phân rã thành các lần dùng trực tiếp trên class. Cơ chế scan của processor cần được thiết kế phù hợp.

### Trường hợp B: thư viện Java Core tự đọc annotation ở runtime

Cần:

1. Annotation trên class được khai báo `@Retention(RUNTIME)`.
2. Meta-annotation muốn đọc cũng có retention `RUNTIME`.
3. Code truy vấn đúng annotation type, tự duyệt các tầng và bảo vệ khỏi chu trình nếu cần.
4. Định nghĩa quy tắc ưu tiên nếu có nhiều marker hoặc thuộc tính mâu thuẫn.
5. Không nhầm **truy cập meta-annotation ở annotation type** với **annotation trực tiếp trên class**.

Nếu chỉ cần một thông tin đơn giản, đôi khi dùng `@RequiredRole` trực tiếp lên class sẽ rõ hơn tạo một annotation tổng hợp và viết hẳn một resolver mới.

### Trường hợp C: framework hỗ trợ composed annotation

Cần:

1. Chọn cơ chế **được framework tài liệu hóa**; không tự giả định `Class.getAnnotation` có tính năng merge.
2. Kiểm tra `@Target`, `@Retention`, kiểu element và default value của từng annotation trong chuỗi.
3. Kiểm tra cách framework phát hiện stereotype, tìm kiếm meta-annotation, kế thừa và quy tắc attribute alias.
4. Nếu framework có nhiều phiên bản, viết test tích hợp trên các version cần hỗ trợ.
5. Không khẳng định việc chỉ thêm annotation sẽ kích hoạt hành vi khi chưa bật component scanning, transaction processing, web mapping hoặc cấu hình tương ứng.

**Thiết kế tốt là giữ ranh giới rõ:** Java quy định metadata hợp lệ; processor/framework quyết định cách diễn giải metadata đó.

## 13. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Nghĩ `@MyAnnotation` có meta-annotation `@Policy` thì `MyClass.class.getAnnotation(Policy.class)` tự trả `Policy`. | Java Reflection chuẩn không tự flatten meta-annotation tùy biến. | Đọc `MyAnnotation.class` hoặc dùng framework resolver. |
| Cho rằng mọi annotation dùng trên annotation khác là annotation chuẩn của Java. | Annotation nghiệp vụ cũng có thể là meta-annotation theo nghĩa cú pháp. | Phân biệt meta-annotation **chuẩn** và meta-annotation **tùy biến**. |
| Chỉ dùng `@Retention(RUNTIME)` trên marker ở tầng trong. | Annotation ở tầng ngoài có retention riêng, có thể mặc định `CLASS`. | Cấu hình retention cho từng kiểu cần Reflection. |
| Chỉ dùng `@Target(ANNOTATION_TYPE)` trên annotation ở ngoài nhưng muốn gắn nó lên class. | Target của annotation ngoài không cho class. | Đặt target phù hợp nơi sử dụng thực tế. |
| Xem `@Inherited` là cơ chế tìm annotation từ interface và mọi meta-level. | Java chỉ có quy tắc kế thừa hẹp qua superclass. | Dùng API tìm kiếm phù hợp nếu framework yêu cầu interface/hierarchy. |
| Nhầm `@Repeatable` với việc tổng hợp nhiều loại annotation khác nhau. | `@Repeatable` là container cho **cùng một annotation type**. | Dùng composition/processor khi muốn gộp nhiều loại metadata. |
| Mong `@Service` meta-annotation tự được `javac` đưa thành `@Component` trên class. | Java compiler không thực hiện composition của Spring. | Để Spring component scanner/metadata resolver xử lý. |
| Dùng `@AliasFor` nhưng chỉ gọi `Class.getAnnotation` của Java Core. | Alias là ngữ nghĩa của Spring. | Dùng API merged annotation do framework cung cấp. |
| Đoán rằng hai thuộc tính trùng tên tự override nhau ở mọi framework. | Attribute mapping có quy tắc và version cụ thể. | Khai báo rõ alias nếu cần, xem tài liệu/test framework. |
| Dùng `@Transactional` meta-annotation mà không cấu hình transaction management. | Metadata không tự biến thành transaction runtime. | Kiểm tra cấu hình, cơ chế proxy/interception và điều kiện framework. |
| Thấy Reflection trả `null` rồi cho rằng meta-annotation không có trong bytecode. | Có thể đang hỏi sai `AnnotatedElement` hoặc sai retention. | Kiểm tra annotation ở chính annotation type và runtime retention. |
| Viết resolver đệ quy mà không chống chu trình hoặc không quyết định ưu tiên. | Các chuỗi meta-annotation có thể lồng sâu/trùng nhiều nhánh. | Theo dõi visited, định nghĩa precedence, tests cho conflict. |

## 14. Tự kiểm tra kiến thức

Dựa trên chương trình `CoreMetaVsComposedDemo.java` ở mục 5:

1. **Vì sao `AdminPage.class.getAnnotation(RequiredRole.class)` là `null`?** Vì `RequiredRole` được đặt trên khai báo `AdminOnly`, không trực tiếp trên `AdminPage`, và Java Reflection chuẩn không tự merge meta-annotation tùy biến.
2. **Làm sao đọc được giá trị `"ADMIN"` chỉ bằng JDK?** Lấy `AdminOnly.class.getAnnotation(RequiredRole.class).value()` hoặc lấy `AdminOnly` từ class rồi hỏi `annotationType()`.
3. **Nếu bỏ `@Retention(RUNTIME)` khỏi `AdminOnly`, điều gì xảy ra?** Nó mặc định `CLASS`; chương trình không còn lấy được `AdminOnly` trên `AdminPage` bằng Reflection runtime thông thường.
4. **Nếu bỏ `@Retention(RUNTIME)` khỏi `RequiredRole`?** Lần đọc `RequiredRole` từ `AdminOnly.class` không còn thấy annotation ấy qua Reflection runtime.
5. **`@Inherited` có khiến class được implements interface gắn `@Tracked` có `@Tracked` không?** Không; đây không phải quy tắc của Java Core.
6. **`@Documented` có phải Spring composed annotation không?** Không; nó là meta-annotation chuẩn của Java phục vụ tài liệu.
7. **`@Repeatable` có cho phép alias từ `@AdminOnly.value()` sang `@RequiredRole.value()` không?** Không; nó giải quyết việc dùng cùng một annotation type nhiều lần.
8. **Spring làm gì mà `Class.getAnnotation` của Java không tự làm?** Có thể tìm kiếm theo nhiều tầng meta-annotation và hợp nhất các thuộc tính/alias theo mô hình annotation của Spring.
9. **Tại sao `@TransactionalService` chưa bảo đảm transaction hoạt động khi chỉ có source Java?** Vì phải có Spring và các cơ chế xử lý transaction được cấu hình/áp dụng đúng.
10. **Khi nào nên dùng annotation trực tiếp thay vì một composed annotation?** Khi chỉ cần một ý nghĩa đơn giản, không có nhu cầu nhóm cấu hình hoặc không có resolver/framework hỗ trợ.
11. **Làm sao kiểm tra composed annotation có hoạt động thực tế?** Viết integration test với API và cấu hình đúng của framework, không chỉ biên dịch được Java source.
12. **Kết luận:** Java Core quy định **cú pháp và một số ngữ nghĩa meta-annotation tiêu chuẩn**; framework có thể xây **ngữ nghĩa tổng hợp cao hơn** trên cùng metadata, nhưng các hành vi đó không tự động trở thành quy tắc của `javac` hay Java Reflection.

## 15. Tài liệu chuẩn để đối chiếu

- [Java SE 17 – `java.lang.annotation.Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html): nơi annotation có thể được sử dụng, nhất là `ANNOTATION_TYPE`.
- [Java SE 17 – `java.lang.annotation.Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): vòng đời SOURCE/CLASS/RUNTIME.
- [Java SE 17 – `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): giới hạn kế thừa theo superclass.
- [Java SE 17 – `java.lang.annotation.Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): annotation lặp qua container.
- [Java SE 17 – `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): phân biệt directly present, indirectly present, present và các phương thức truy xuất annotation.
- [Spring Framework – Annotation Programming Model](https://github.com/spring-projects/spring-framework/wiki/Spring-Annotation-Programming-Model): meta-annotations, composed annotations, stereotype, attribute aliases và overrides.
- [Spring Framework – `MergedAnnotations` API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/MergedAnnotations.html): các khả năng tìm kiếm và hợp nhất annotation của framework.

Ghi nhớ: **“meta-annotation” mô tả nơi đặt annotation; “composed annotation” mô tả cách dùng và xử lý một tổ hợp annotation.** Java cung cấp nền tảng, còn những hành vi tự động ngoài hợp đồng Java phải đến từ processor hoặc framework cụ thể.
