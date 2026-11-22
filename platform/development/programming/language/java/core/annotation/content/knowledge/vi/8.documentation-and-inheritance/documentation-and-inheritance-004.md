# Giới hạn kế thừa annotation: không truyền từ giao diện, phương thức hoặc trường

## 1. Hiểu đúng `@Inherited` trong Java

Trong Java, **kế thừa lớp**, **kế thừa thành viên** và **tra cứu annotation được kế thừa** là các cơ chế khác nhau. Một phương thức có thể được lớp con kế thừa về mặt gọi phương thức, nhưng điều đó không có nghĩa metadata của phương thức ấy được sao chép sang phương thức mới. Đây là nguyên nhân của nhiều nhầm lẫn khi dùng meta-annotation `@Inherited`.

`@Inherited` nằm trong package `java.lang.annotation`. Nó được gắn lên **khai báo một loại annotation** để đánh dấu rằng annotation loại đó có thể được **tra cứu theo chuỗi lớp cha** trong những điều kiện nhất định:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("parent")
class Parent {}

class Child extends Parent {}
```

Với đoạn mã này, `Child.class.getAnnotation(Category.class)` có thể tìm được `@Category("parent")` từ `Parent` khi `Child` không trực tiếp có `@Category`. Nhưng `Child.class.getDeclaredAnnotation(Category.class)` vẫn trả về `null` vì `Child` **không khai báo trực tiếp** annotation đó.

**Giới hạn trung tâm của bài:** `@Inherited` chỉ có ý nghĩa kế thừa trên **khai báo lớp** theo chuỗi superclass. Nó **không** làm annotation truyền từ interface được implement, không làm annotation truyền từ phương thức được override và không làm annotation truyền sang trường được khai báo lại trong lớp con.

## 2. Chính xác điều kiện nào làm annotation được tra cứu từ lớp cha?

Giả sử có annotation loại `A` với `@Inherited`:

1. Annotation loại `A` được gắn trực tiếp lên một **khai báo class** ở phía superclass.
2. Một class con đang được hỏi về `A`, nhưng bản thân class đó **không khai báo trực tiếp** `A`.
3. Khi tra cứu bằng các phương thức Reflection có xét kế thừa, chẳng hạn `Class.getAnnotation(A.class)` hoặc `Class.getAnnotations()`, Java có thể tiếp tục theo **superclass chain** để tìm `A`.
4. Nếu lớp con trực tiếp khai báo annotation cùng loại, giá trị trực tiếp của lớp con được ưu tiên; không tự trộn các phần tử với annotation ở lớp cha.

Để quan sát bằng Reflection trong lúc chạy, loại annotation cần có `@Retention(RetentionPolicy.RUNTIME)`. Nếu không đặt retention, mặc định là `CLASS` và Reflection thông thường không đọc được metadata gắn trên lớp cha.

Có thể hình dung:

```text
@Category("base")
class Base {}
      |
      | extends
      v
class Intermediate extends Base {}
      |
      | extends
      v
class FinalChild extends Intermediate {}

FinalChild.class.getAnnotation(Category.class)
    -> có thể tìm @Category("base") từ Base

FinalChild.class.getDeclaredAnnotation(Category.class)
    -> null: FinalChild không trực tiếp khai báo Category
```

`@Inherited` **không thực sự sao chép source annotation vào khai báo lớp con**. Nó tác động tới quy tắc **tra cứu metadata**. Khi dùng `javap -v` trên class con không có annotation trực tiếp, đừng kỳ vọng phải thấy một bản sao annotation từ class cha trong chính tệp `.class` của lớp con.

### Hai API Reflection dễ nhầm

| API trên đối tượng `Class` | Có xét superclass khi annotation type có `@Inherited`? | Ý nghĩa |
| --- | --- | --- |
| `getAnnotation(A.class)` | Có, trong điều kiện hợp lệ | Trả annotation trực tiếp hoặc loại được kế thừa từ class cha |
| `getAnnotations()` | Có, với annotation được kế thừa | Liệt kê annotation trực tiếp và annotation kế thừa hợp lệ |
| `getDeclaredAnnotation(A.class)` | Không | Chỉ annotation trực tiếp trên class đang xét |
| `getDeclaredAnnotations()` | Không | Chỉ annotation được khai báo trực tiếp |
| `isAnnotationPresent(A.class)` | Có, theo quy tắc của `getAnnotation` | Kiểm tra sự hiện diện với cơ chế tra cứu tương ứng |

Đây là các API của `Class`. Đừng áp dụng quy tắc này một cách máy móc cho `Method`, `Field` hay mọi API của framework.

## 3. Không kế thừa annotation từ interface

Xét một interface được gắn annotation loại có `@Inherited`:

```java
// Các đoạn dưới đây dùng chung khai báo @Category ở mục 2.
@Category("contract")
interface PaymentContract {}

class PaymentService implements PaymentContract {}
```

Dù `PaymentService` implements `PaymentContract`, các lời gọi thông thường:

```java
PaymentContract.class.getAnnotation(Category.class); // có Category
PaymentService.class.getAnnotation(Category.class);  // null
```

Giải thích: **kế thừa theo `@Inherited` chỉ đi theo chuỗi superclass của class**, không đi theo `implements` hoặc `extends` giữa các interface. Việc interface là một kiểu Java không khiến metadata gắn trên khai báo interface trở thành annotation được kế thừa trên class triển khai.

Điều này cũng áp dụng nếu `PaymentService` implement nhiều interface cùng gắn `@Category`; Reflection chuẩn không chọn một interface để “thừa hưởng” annotation ấy.

Đặc biệt, khi **một interface mở rộng interface khác**, `@Inherited` không khiến annotation tự xuất hiện trên interface con qua `Class.getAnnotation` theo quy tắc superclass của class. Nếu framework muốn tìm annotation theo **interface hierarchy**, framework phải cung cấp cơ chế quét/tra cứu riêng.

**Tình huống Spring và các framework:** một số framework có hệ thống tìm annotation theo interface, meta-annotation hoặc các cấu trúc được tổng hợp. Kết quả tra cứu do framework quy định có thể rộng hơn Java Reflection trực tiếp; không được xem đó là bằng chứng rằng `@Inherited` của ngôn ngữ hỗ trợ interface.

## 4. Không truyền annotation từ phương thức cha sang phương thức override

Xét trường hợp:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Trace {
    String value();
}

class BaseHandler {
    @Trace("base")
    public void handle() {}
}

class DerivedHandler extends BaseHandler {
    @Override
    public void handle() {}
}
```

Ở đây, `@Trace` được phép gắn cả trên class lẫn method bởi `@Target`. Nhưng `@Inherited` **chỉ tác động tới annotation trên khai báo lớp**. Nó **không khiến `DerivedHandler.handle()` thừa hưởng `@Trace("base")`** từ `BaseHandler.handle()`.

Nếu lấy chính phương thức override:

```java
DerivedHandler.class
    .getDeclaredMethod("handle")
    .getAnnotation(Trace.class); // null
```

`@Override` chỉ khẳng định phương thức có quan hệ override hợp lệ; nó **không liên quan tới việc sao chép annotation** trên phương thức cha. Nếu logic xử lý cần một annotation trên phương thức override, phải gắn trực tiếp ở phương thức đó hoặc viết consumer chủ động dò về phương thức tương ứng ở superclass/interface.

### Vì sao đôi khi tìm method “kế thừa” vẫn thấy annotation?

Có một tình huống cần phân biệt rất rõ. Giả sử `BaseHandler` có `public void process()` được gắn `@Trace`, còn `DerivedHandler` **không override `process()`**. Khi gọi:

```java
DerivedHandler.class.getMethod("process")
```

Reflection có thể trả về đối tượng `Method` **khai báo tại `BaseHandler`**, vì `getMethod` tra cứu cả phương thức `public` được kế thừa. Khi tiếp tục gọi `getAnnotation(Trace.class)` trên `Method` đó, ta đang đọc annotation **trực tiếp của method cha**, không phải một annotation vừa được Java truyền qua method override.

Dùng `method.getDeclaringClass()` để phân biệt. Nếu trả về `BaseHandler.class` thì `Method` đại diện cho khai báo gốc. Nếu lớp con có override thì nó có khai báo `Method` riêng, và annotation của method cha không tự đi theo.

## 5. Không truyền annotation sang trường của lớp con

Một trường `field` là một vị trí khai báo riêng. Xét:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD})
@interface ColumnLabel {
    String value();
}

class BaseRecord {
    @ColumnLabel("ID")
    public String id;

    @ColumnLabel("CODE")
    public String code;
}

class ChildRecord extends BaseRecord {
    // Khai báo lại tên 'code': đây là field hiding, không phải override.
    public String code;
}
```

Trên `ChildRecord`, hai điều sau khác nhau:

- `ChildRecord.class.getField("id")` có thể trả về `Field` **khai báo tại `BaseRecord`**, vì `id` là trường `public` được kế thừa và không bị che khuất. Annotation được thấy là annotation **trực tiếp trên trường cha**.
- `ChildRecord.class.getDeclaredField("code")` trả về trường `code` do `ChildRecord` tự khai báo, **không có `@ColumnLabel`**. Annotation trên `BaseRecord.code` không chuyển sang trường khai báo lại.

Java **không override field** theo cách override method; một field cùng tên ở subclass thực hiện **field hiding**. Cả hai trường là hai khai báo riêng biệt, và metadata không tự sao chép.

Tương tự, một annotation gắn trên **tham số, constructor hoặc method** không tự truyền tới thành phần cùng tên/kiểu trong lớp con chỉ vì mối quan hệ kế thừa của các class.

## 6. Ví dụ Java 17+ đầy đủ: lớp, interface, override và field

Tạo tệp **`InheritedBoundariesDemo.java`**. Chương trình sau chạy độc lập bằng Java 17+, không cần Spring/JUnit. Cùng một loại annotation `@Trace` được phép gắn trên khai báo type, method và field để chứng minh rằng **mặc dù vị trí gắn đều hợp lệ, chỉ annotation gắn trên class mới tham gia cơ chế `@Inherited`**.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.FIELD})
@interface Trace {
    String value();
}

@Trace("interface-type")
interface JobContract {
    @Trace("interface-method")
    void perform();
}

@Trace("parent-type")
class ParentJob {
    @Trace("parent-method")
    public void unchanged() {}

    @Trace("parent-overridden")
    public void overridden() {}

    @Trace("parent-field")
    public String visible;

    @Trace("parent-hidden")
    public String hidden;
}

class ChildJob extends ParentJob {
    @Override
    public void overridden() {}

    public String hidden;
}

class ContractJob implements JobContract {
    @Override
    public void perform() {}
}

public class InheritedBoundariesDemo {
    public static void main(String[] args)
            throws NoSuchMethodException, NoSuchFieldException {

        Trace inheritedType = ChildJob.class.getAnnotation(Trace.class);
        System.out.println("Child class: " + inheritedType.value());
        System.out.println("Child declared: "
                + (ChildJob.class.getDeclaredAnnotation(Trace.class) != null));

        System.out.println("Interface itself: "
                + JobContract.class.getAnnotation(Trace.class).value());
        System.out.println("Interface to class: "
                + (ContractJob.class.getAnnotation(Trace.class) != null));

        Method overridden = ChildJob.class.getDeclaredMethod("overridden");
        System.out.println("Overridden method: "
                + (overridden.getAnnotation(Trace.class) != null));

        Method unchanged = ChildJob.class.getMethod("unchanged");
        System.out.println("Inherited method owner: "
                + unchanged.getDeclaringClass().getSimpleName());
        System.out.println("Inherited method marker: "
                + unchanged.getAnnotation(Trace.class).value());

        Field hidden = ChildJob.class.getDeclaredField("hidden");
        System.out.println("Hidden field: "
                + (hidden.getAnnotation(Trace.class) != null));

        Field visible = ChildJob.class.getField("visible");
        System.out.println("Inherited field owner: "
                + visible.getDeclaringClass().getSimpleName());
        System.out.println("Inherited field marker: "
                + visible.getAnnotation(Trace.class).value());

        Method implemented = ContractJob.class.getDeclaredMethod("perform");
        System.out.println("Interface method to implementation: "
                + (implemented.getAnnotation(Trace.class) != null));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac -encoding UTF-8 InheritedBoundariesDemo.java
java InheritedBoundariesDemo
```

Kết quả stdout:

```text
Child class: parent-type
Child declared: false
Interface itself: interface-type
Interface to class: false
Overridden method: false
Inherited method owner: ParentJob
Inherited method marker: parent-method
Hidden field: false
Inherited field owner: ParentJob
Inherited field marker: parent-field
Interface method to implementation: false
```

### Đọc kết quả đúng bản chất

**Class con:**
- `ChildJob.class.getAnnotation(Trace.class)` tìm thấy `@Trace("parent-type")` từ `ParentJob` do `Trace` có `@Inherited`, được gắn trên **class cha** và có `RUNTIME`.
- `ChildJob.class.getDeclaredAnnotation(Trace.class)` trả về `null`, bởi `ChildJob` không được gắn `@Trace` trực tiếp.

**Interface:**
- `JobContract.class.getAnnotation(Trace.class)` đọc annotation **trực tiếp** trên khai báo interface.
- `ContractJob.class.getAnnotation(Trace.class)` trả về `null`; `implements JobContract` không kích hoạt `@Inherited`.

**Method:**
- `ChildJob.overridden()` là một khai báo method mới trong class con, không có annotation dù method cha đã gắn `@Trace`.
- `ChildJob.class.getMethod("unchanged")` tìm thấy method public **thực sự được khai báo ở `ParentJob`**; dòng `getDeclaringClass()` xác nhận nguồn. Annotation đọc được là của method ấy.

**Field:**
- `ChildJob.hidden` là field mới che khuất field cùng tên ở cha, nên annotation trên field cha không tự truyền.
- `ChildJob.class.getField("visible")` trả về field public **được khai báo ở `ParentJob`**; annotation là metadata trực tiếp của field cha.

**Method từ interface:**
- `ContractJob.perform()` hiện thực phương thức trong interface, nhưng annotation trên `JobContract.perform()` không được sao chép sang phương thức của class triển khai.

Bài học không nằm ở chỗ “Reflection luôn trả null cho method/field kế thừa”. **Nếu Reflection trả về đúng đối tượng `Method` hoặc `Field` của superclass, annotation trực tiếp trên đối tượng gốc vẫn đọc được.** Điều không xảy ra là **truyền metadata sang một khai báo mới của subclass**.

## 7. Bảng quyết định: nhìn đúng thành phần được hỏi

| Tình huống | Có nhận annotation qua `@Inherited` không? | Cách giải thích |
| --- | --- | --- |
| Class con không gắn annotation, superclass gắn loại annotation có `@Inherited` | **Có**, khi Reflection tra cứu class phù hợp | Chỉ đường đi theo superclass |
| Class implement interface đã gắn annotation | **Không** | Interface không thuộc chuỗi superclass để kế thừa annotation |
| Interface con extends interface cha có annotation | **Không** qua quy tắc `@Inherited` | Không phải class inheritance |
| Method con override method cha đã gắn annotation | **Không** | Method con là khai báo riêng |
| Class con chỉ kế thừa method public và không override | **Không có propagation**; vẫn có thể đọc annotation của method cha | `getMethod` có thể trả về method gốc của superclass |
| Field con khai báo lại cùng tên với field cha có annotation | **Không** | Hai field khác nhau; field hiding |
| Class con truy vấn field public chưa bị che khuất trong superclass | **Không có propagation**; vẫn có thể đọc annotation của field cha | `getField` có thể trả về field gốc |
| Class con khai báo trực tiếp annotation cùng loại | Giá trị trực tiếp được ưu tiên | Không cần kế thừa từ superclass |

Đây là quy tắc Reflection chuẩn. Một thư viện có API truy tìm annotation riêng có thể tìm rộng hơn, nhưng cần kiểm tra tài liệu và cơ chế cụ thể trước khi áp dụng.

## 8. Các hiểu nhầm thường gặp

### “`@Inherited` truyền mọi annotation ở mọi thành phần.”

Sai. `@Inherited` chỉ quy định kế thừa **annotation trên khai báo class**. Nó không làm mọi `Method`, `Field`, parameter và interface tự sở hữu annotation của thành phần ở bậc cha.

### “`@Target(METHOD)` cộng `@Inherited` nghĩa là method override kế thừa annotation.”

Sai. `@Target` chỉ xác định vị trí được gắn annotation; `@Inherited` vẫn chỉ có ý nghĩa trên khai báo class. Cho phép gắn marker lên method không làm mở rộng ngữ nghĩa kế thừa.

### “`getMethod` thấy annotation thì chắc chắn subclass method đã kế thừa metadata.”

Sai. `getMethod` có thể trả về phương thức public ở superclass. Hãy đọc `method.getDeclaringClass()`; nếu là superclass, bạn đang xem annotation của method cha, không phải metadata trên một override trong subclass.

### “Field và method kế thừa theo cùng cách.”

Không đúng. Method có thể được override; field có thể bị *hide* bằng khai báo trùng tên. Dù là cơ chế nào, **khai báo mới** không tự có annotation từ khai báo cũ.

### “Annotation trên interface không tác dụng gì.”

Khẳng định này cũng sai. Annotation trên interface vẫn có thể được đọc **trực tiếp trên chính interface**, và framework/processor có thể chủ động tìm theo cây interface. Nó chỉ không được **Java `@Inherited` tự truyền** sang class implement.

### “Đã có `@Inherited` thì bất kể retention nào cũng dùng Reflection tra cứu được.”

Sai. Nếu cần quan sát khi chạy bằng Reflection, annotation phải có `@Retention(RetentionPolicy.RUNTIME)`. `@Inherited` không thay thế `@Retention`.

### “Đã dùng interface framework thì hành vi Reflection chuẩn cũng thay đổi.”

Không. Framework có thể thiết kế hệ thống annotation lookup riêng. Khi giải thích một kết quả, phải biết đang dùng `Class.getAnnotation` của Java, một API tiện ích của framework hay processor tại compile-time.

## 9. Nếu ứng dụng cần “kế thừa” annotation của method hoặc interface thì làm thế nào?

Với yêu cầu như *“method implement hợp đồng interface phải mang cùng chính sách audit”*, có hai hướng:

- **Gắn annotation ở đúng khai báo mà consumer xử lý**, ví dụ gắn lên method triển khai hoặc override. Cách này rõ ràng, phù hợp khi số nơi sử dụng ít và tránh phụ thuộc vào thuật toán tra cứu riêng.
- **Thiết kế consumer chủ động tra cứu nguồn khác**, ví dụ tìm method cùng chữ ký trong superclass và interface, hoặc tìm annotation trên interface mà class implement. Khi làm vậy cần xác định thứ tự ưu tiên, quan hệ override, overload, bridge methods, generic methods, nhiều interface mang metadata trái nhau và các quy tắc của framework liên quan.

Với mã sử dụng Reflection thuần, `Method.getAnnotation(...)` không tự chạy thuật toán tìm cả interface hierarchy và superclass methods. Nếu một thư viện báo rằng nó *tìm thấy* annotation ở interface hoặc method cha, hãy kiểm tra logic thư viện: điều đó chứng minh **consumer làm thêm việc**, chứ không làm thay đổi ý nghĩa của `@Inherited` trong Java.

Ngược lại, nếu chỉ muốn chia sẻ annotation **ở mức class** giữa superclass và subclass, `@Inherited` cộng `RUNTIME` thường là cơ chế chuẩn thích hợp, miễn quan hệ là `extends` giữa các class.

## 10. Bài tập tự kiểm tra

**Bài 1.** `@Inherited @Retention(RUNTIME) @interface Label {}` được gắn trên `interface Marker {}`. `class A implements Marker {}` có được `A.class.getAnnotation(Label.class)` trả về không?

**Đáp án:** Không, vì `@Inherited` không truyền annotation từ interface sang class implement.

**Bài 2.** `Base.run()` có `@Trace`, còn `Child.run()` override nhưng không gắn `@Trace`. `Child.class.getDeclaredMethod("run").getAnnotation(Trace.class)` có thấy metadata từ Base không?

**Đáp án:** Không. `Child.run()` là một method declaration riêng.

**Bài 3.** `Child` không override `Base.execute()`. Vì sao `Child.class.getMethod("execute")` có thể đọc được annotation mà `Base.execute()` mang?

**Đáp án:** `getMethod` có thể trả về đối tượng `Method` được khai báo tại `Base`. Annotation là metadata **trực tiếp của method Base**; kiểm chứng qua `getDeclaringClass()`.

**Bài 4.** `Child` có field `code` mới cùng tên field được annotate ở `Base`. Annotation có tự xuất hiện trên `Child.code` không?

**Đáp án:** Không. Field hiding tạo một declaration khác; `@Inherited` không sao chép annotation từ field cha.

**Bài 5.** `Child.class.getAnnotation(Label.class)` thấy annotation từ `Base`, nhưng `Child.class.getDeclaredAnnotation(Label.class)` trả về `null`. Có mâu thuẫn không?

**Đáp án:** Không. API đầu xét cơ chế tìm annotation kế thừa trên class; API sau chỉ đọc annotation trực tiếp của class hiện tại.

**Bài 6.** Một framework tìm được annotation ở interface khi một class implement interface ấy. Điều đó có chứng minh rằng `@Inherited` của Java hỗ trợ interface không?

**Đáp án:** Không. Framework có thể có thuật toán tra cứu interface riêng, vượt phạm vi tra cứu mặc định của Java Reflection.

**Ghi nhớ:** `@Inherited` hỗ trợ tra cứu annotation theo **superclass của class**, không sao chép metadata sang interface implement, method override hay field bị che khuất. Nếu thấy annotation trên một method hoặc field “được kế thừa”, hãy xác minh đó có phải chính khai báo ở superclass được Reflection trả về hay không.
