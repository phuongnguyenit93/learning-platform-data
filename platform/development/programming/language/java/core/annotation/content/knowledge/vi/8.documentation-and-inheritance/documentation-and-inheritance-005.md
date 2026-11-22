# Annotation khai báo tại lớp con che annotation cùng kiểu ở lớp cha

Trong Java Core, nếu một annotation type được đánh dấu `@Inherited`, Reflection trên một **class** có thể tìm annotation loại đó ở superclass khi class đang xét không khai báo annotation tương ứng. Nhưng khi **class con trực tiếp khai báo annotation cùng kiểu**, khai báo ở class con được ưu tiên và annotation của superclass bị **che khuất trong kết quả tra cứu**. Giá trị của hai annotation không được tự động cộng gộp hoặc hợp nhất.

Đây là một quy tắc về cách Java xác định annotation **hiện diện** khi truy vấn class, chứ không phải việc class con xóa hay sửa metadata trong file `.class` của class cha.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích điều kiện có thể kế thừa annotation class trong Java: annotation type phải có `@Inherited` và retention thích hợp nếu đọc bằng Reflection lúc chạy.
- Dự đoán annotation được trả về khi class con không khai báo, khi class con khai báo cùng kiểu, và khi có nhiều tầng kế thừa.
- Hiểu vì sao annotation khai báo ở class con **thay thế toàn bộ giá trị annotation cùng kiểu được kế thừa**, còn element không ghi trong annotation con dùng `default` của annotation type.
- So sánh `getAnnotation(...)` với `getDeclaredAnnotation(...)`, `getAnnotations()` và `getDeclaredAnnotations()`.
- Phân biệt annotation kế thừa ở class với annotation ở interface, method, field và các annotation lặp.
- Kiểm chứng bằng ví dụ Java 17+ tự biên dịch/chạy.

## 2. Điều kiện tiên quyết: `@Inherited` hoạt động ra sao?

Ví dụ khai báo một annotation dùng để mô tả chế độ xử lý:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Mode {
    String value();
    int level() default 1;
}
~~~

Đây là **khai báo minh họa**; chương trình hoàn chỉnh xuất hiện bên dưới.

Ba meta-annotation có vai trò riêng:

- `@Inherited`: cho phép cơ chế truy vấn annotation trên class đi tìm trong chuỗi **superclass** khi cần.
- `@Retention(RetentionPolicy.RUNTIME)`: lưu annotation để Reflection lúc chạy có thể đọc. Nếu không khai báo retention thì mặc định `CLASS` và Reflection thông thường không đọc được.
- `@Target(ElementType.TYPE)`: cho phép gắn annotation trên khai báo kiểu (trong ví dụ, trên class); target không tự tạo hành vi kế thừa.

`@Inherited` chỉ có ý nghĩa đối với annotation gắn trên khai báo **class** khi Java tra cứu kiểu annotation đó ở class con. Nó không làm annotation gắn lên interface, method, field hoặc parameter tự động được kế thừa theo quy tắc này.

Với một annotation type không được gắn `@Inherited`, Reflection trên class con không tự tìm annotation của superclass chỉ vì class con dùng `extends`.

## 3. Trường hợp 1: class con không khai báo annotation

Giả sử:

~~~java
@Mode(value = "base", level = 7)
class Base {}

class NoTag extends Base {}
~~~

`Base` khai báo trực tiếp `@Mode(value = "base", level = 7)`. `NoTag` không có `@Mode` riêng. Vì `Mode` được đánh dấu `@Inherited`, khi truy vấn:

~~~java
Mode inherited = NoTag.class.getAnnotation(Mode.class);
System.out.println(inherited.value()); // base
System.out.println(inherited.level()); // 7
~~~

Reflection lấy giá trị từ annotation trên `Base`.

Tuy nhiên:

~~~java
Mode declared = NoTag.class.getDeclaredAnnotation(Mode.class);
System.out.println(declared); // null
~~~

Kết quả `null` là đúng vì `NoTag` **không trực tiếp khai báo** `@Mode`.

Khác biệt cần ghi nhớ:

- `getAnnotation(Mode.class)` trả một annotation được coi là **hiện diện** theo quy tắc API, có thể đến từ superclass nếu `@Inherited` áp dụng.
- `getDeclaredAnnotation(Mode.class)` chỉ xét phần tử hiện tại, không tra superclass.

Không nên hiểu rằng compiler đã sao chép `@Mode` từ `Base` sang `NoTag.class`. Annotation của cha vẫn thuộc về cha; API Reflection định nghĩa cách tra cứu để trả kết quả kế thừa.

## 4. Trường hợp 2: class con khai báo cùng kiểu và che annotation cha

Vẫn với `Base`, khai báo class con:

~~~java
@Mode("child")
class Child extends Base {}
~~~

Bây giờ `Child` có một `@Mode` riêng. Truy vấn:

~~~java
Mode mode = Child.class.getAnnotation(Mode.class);
System.out.println(mode.value()); // child
System.out.println(mode.level()); // 1
~~~

Kết quả:

- `value()` là `"child"`, được khai báo ngay trên `Child`.
- `level()` là `1`, được lấy từ **`Mode.level() default 1`**.
- `level = 7` của annotation trên `Base` **không được hợp nhất** vào annotation ở `Child`.

Đây chính là ý nghĩa của việc annotation ở lớp con **che annotation cùng kiểu ở lớp cha**. Cơ chế tìm kiếm thấy annotation phù hợp ngay tại lớp con, nên không tiếp tục lấy annotation cùng kiểu ở superclass để ghép element.

So sánh trực quan:

| Class | Annotation trực tiếp | `getAnnotation(Mode.class)` | `getDeclaredAnnotation(Mode.class)` |
| --- | --- | --- | --- |
| `Base` | `@Mode(value="base", level=7)` | `base:7` | `base:7` |
| `NoTag extends Base` | Không có | `base:7` (kế thừa khi tra cứu) | `null` |
| `Child extends Base` | `@Mode("child")` | `child:1` | `child:1` |
| `Grandchild extends Child` | Không có | `child:1` (từ `Child`) | `null` |

Nếu muốn `Child` giữ lại `level = 7`, phải **ghi tường minh** `@Mode(value = "child", level = 7)` hoặc xây dựng logic xử lý riêng để hợp nhất cấu hình. Java Reflection tiêu chuẩn không tự làm việc hợp nhất đó.

### Khi có nhiều superclass liên tiếp

~~~java
class Grandchild extends Child {}
~~~

`Grandchild` không khai báo `@Mode`, nên Reflection đi lên chuỗi superclass và gặp `@Mode("child")` trên `Child` trước. Kết quả là `child:1`, **không phải** `base:7`.

Điều này tạo quy tắc dễ nhớ: với annotation type kế thừa được, **khai báo gần nhất trên đường đi từ class đang xét lên superclass có hiệu lực trong kết quả tìm kiếm một annotation cùng kiểu**. Khi class đang xét tự khai báo, chính nó là nơi gần nhất.

Class cha vẫn giữ annotation của mình: `Base.class.getAnnotation(Mode.class)` tiếp tục trả `base:7`, dù có bao nhiêu lớp con khai báo `@Mode` khác.

## 5. Ví dụ Java 17+ chạy độc lập

Tạo đúng một file tên **`InheritedShadowDemo.java`** và lưu toàn bộ chương trình dưới đây. Không khai báo `package` để có thể chạy trực tiếp ở thư mục chứa file.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Mode {
    String value();
    int level() default 1;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Owner {
    String value();
}

@Mode(value = "base", level = 7)
@Owner("base-owner")
class Base {}

class NoTag extends Base {}

@Mode("child")
class Child extends Base {}

class Grandchild extends Child {}

@Mode("interface")
interface Contract {}

class ImplementsContract implements Contract {}

public class InheritedShadowDemo {
    public static void main(String[] args) {
        Mode base = Base.class.getAnnotation(Mode.class);
        Mode noTag = NoTag.class.getAnnotation(Mode.class);
        Mode child = Child.class.getAnnotation(Mode.class);
        Mode grandchild = Grandchild.class.getAnnotation(Mode.class);

        System.out.println("base=" + base.value()
                + ":" + base.level());
        System.out.println("noTag=" + noTag.value()
                + ":" + noTag.level());
        System.out.println("noTagDeclared="
                + NoTag.class.getDeclaredAnnotation(Mode.class));
        System.out.println("child=" + child.value()
                + ":" + child.level());
        System.out.println("childDeclared="
                + Child.class.getDeclaredAnnotation(Mode.class).value());
        System.out.println("grandchild=" + grandchild.value()
                + ":" + grandchild.level());
        System.out.println("ownerInherited="
                + NoTag.class.isAnnotationPresent(Owner.class));
        System.out.println("interfaceInherited="
                + ImplementsContract.class.isAnnotationPresent(Mode.class));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 InheritedShadowDemo.java
java InheritedShadowDemo
~~~

**Stdout chính xác:**

~~~text
base=base:7
noTag=base:7
noTagDeclared=null
child=child:1
childDeclared=child
grandchild=child:1
ownerInherited=false
interfaceInherited=false
~~~

Ý nghĩa của từng nhóm dòng:

1. `base=base:7`: `Base` khai báo `@Mode` đầy đủ và Reflection đọc chính annotation trực tiếp đó.
2. `noTag=base:7`: `NoTag` không khai báo; `getAnnotation` được phép tra `Base` vì `Mode` có `@Inherited`.
3. `noTagDeclared=null`: `getDeclaredAnnotation` không xét superclass.
4. `child=child:1`: `Child` tự khai báo `@Mode("child")` nên kết quả che annotation cha; `level` lấy mặc định `1`, không lấy `7` từ cha.
5. `childDeclared=child`: `getDeclaredAnnotation` tìm thấy annotation được khai báo ngay tại `Child`.
6. `grandchild=child:1`: `Grandchild` tiếp tục kế thừa annotation gần nhất ở `Child` khi tra cứu.
7. `ownerInherited=false`: `Owner` có retention `RUNTIME` nhưng **không có `@Inherited`**, do đó `@Owner("base-owner")` trên `Base` không tự được thấy trên `NoTag`.
8. `interfaceInherited=false`: `Contract` được gắn `@Mode`, nhưng `ImplementsContract` chỉ `implements Contract`. `@Inherited` **không lấy annotation từ interface được triển khai**.

Ví dụ không tạo bất cứ framework hay logic tự động gắn annotation nào; đây chỉ là hành vi đọc metadata qua Reflection.

## 6. Các API có kết quả khác nhau

Với một đối tượng `Class<?>`, các API Reflection được dùng thường xuyên:

| API | Xử lý kế thừa annotation trên class? | Kết quả với `NoTag` trong ví dụ |
| --- | --- | --- |
| `getAnnotation(Mode.class)` | Có nếu `@Inherited` áp dụng và không có khai báo gần hơn | `@Mode(value="base", level=7)` |
| `getDeclaredAnnotation(Mode.class)` | Không; chỉ trực tiếp | `null` |
| `isAnnotationPresent(Mode.class)` | Theo ngữ nghĩa `getAnnotation` | `true` |
| `getAnnotations()` | Bao gồm những annotation được coi là hiện diện; có thể có annotation kế thừa | Có `Mode` từ `Base` |
| `getDeclaredAnnotations()` | Không tra superclass | Không có `Mode` |
| `getAnnotationsByType(Mode.class)` | Hỗ trợ loại có thể lặp và kế thừa theo quy tắc associated | Một phần tử `Mode` trong ví dụ |
| `getDeclaredAnnotationsByType(Mode.class)` | Chỉ trực tiếp/gián tiếp trên phần tử, không tìm superclass | Mảng độ dài 0 |

Trên `Child`, cả `getAnnotation(Mode.class)` và `getDeclaredAnnotation(Mode.class)` đều tìm được annotation của `Child`, nên không có lý do lấy annotation từ `Base` cho cùng loại.

Hàm trả annotation đơn như `getAnnotation(...)` có thể trả `null`. Khi làm việc với API chung, cần kiểm tra giá trị trước khi gọi các element:

~~~java
Mode mode = SomeClass.class.getAnnotation(Mode.class);
if (mode != null) {
    System.out.println(mode.value());
}
~~~

Đoạn trên minh họa ý tưởng, giả sử `Mode` và `SomeClass` đã được khai báo; không phải file chạy độc lập.

### “Được kế thừa” khác “được khai báo trực tiếp”

Về mặt metadata, `Base` và `Child` đều có declaration annotation của riêng mình. `NoTag` và `Grandchild` không nhất thiết có annotation cùng kiểu được lưu trực tiếp trong class file, dù `getAnnotation` trả về một annotation khi chạy.

Nếu chương trình cần biết người viết class con có **chủ động ghi giá trị riêng** hay chưa, dùng `getDeclaredAnnotation` hoặc `getDeclaredAnnotationsByType` thay vì chỉ dựa vào `getAnnotation`.

Nếu chương trình chỉ cần cấu hình hiệu lực ở cấp class với quy tắc inheritance của Java, `getAnnotation` thường phù hợp hơn. Khi cần merge nhiều tầng hoặc fallback theo element, ứng dụng phải tự thiết kế thuật toán lấy và kết hợp annotation ở từng superclass.

## 7. Không có merge element: giá trị mặc định vẫn đến từ annotation type

Xét lại:

~~~java
@interface IllustrationOnly {
    String name();
    int priority() default 10;
    String[] tags() default {};
}
~~~

Nếu thêm `@Inherited` và `@Retention(RUNTIME)` lên `IllustrationOnly`, rồi superclass dùng `@IllustrationOnly(name = "base", priority = 99, tags = {"shared"})`, subclass khai báo `@IllustrationOnly(name = "child")` thì metadata hiệu lực của subclass sẽ là:

~~~text
name = child
priority = 10
tags = []
~~~

`priority` và `tags` lấy **giá trị mặc định do annotation type khai báo**, không lấy `99` hay `{"shared"}` của superclass. Điều này vẫn đúng dù subclass chỉ cung cấp một element trong annotation của nó.

Nếu subclass hoàn toàn không có `@IllustrationOnly`, kết quả truy vấn kế thừa được có thể chứa các giá trị của annotation trên superclass: `base`, `99`, `{"shared"}`.

Chú ý đoạn `IllustrationOnly` là minh họa cơ chế defaults; nó chưa tự khai báo `@Inherited` và `@Retention` trong code fence. Khi thực hành độc lập phải bổ sung đúng meta-annotations ấy.

## 8. Trường hợp class con khai báo nhiều annotation khác kiểu

Giả sử superclass có `@Mode("base")` và `@Owner("base-owner")`, subclass chỉ thêm một annotation **khác kiểu** `@Component` do chương trình tự định nghĩa. Việc khai báo `@Component` không có nghĩa mọi annotation của superclass biến mất.

Quy tắc che ở đây xét **theo annotation type**:

- Nếu subtype trực tiếp khai báo `Mode`, giá trị `Mode` kế thừa từ superclass bị che trong kết quả truy vấn `Mode`.
- Nếu subtype khai báo một type `Other` khác, phép tra `Mode` vẫn có thể đi lên superclass, miễn là các điều kiện inheritance đáp ứng.
- Annotation type không có `@Inherited` không tự có đường đi kế thừa chỉ vì class con không ghi chú gì.

Vì vậy, không nên nói “lớp con có annotation thì chặn hết annotation ở lớp cha”. Đúng hơn là **khai báo cùng kiểu ảnh hưởng kết quả tìm cùng kiểu**.

## 9. Ranh giới của `@Inherited`

### 9.1. Interface không tham gia chuỗi tra cứu superclass

~~~java
@Mode("contract")
interface ServiceContract {}

class ServiceImpl implements ServiceContract {}
~~~

Kể cả `Mode` có `@Inherited`, `ServiceImpl.class.getAnnotation(Mode.class)` **không** tự tìm qua `ServiceContract`. Annotation trên interface và annotation trên superclass không có cùng quy tắc Reflection inheritance.

Nếu framework muốn lấy annotation từ interface hoặc các interface mà superclass triển khai, framework phải tự duyệt cây kiểu và thiết lập quy tắc ưu tiên.

### 9.2. Method override không tự được “thừa kế annotation” theo `@Inherited`

~~~java
class ParentOperation {
    @Deprecated
    public void execute() {}
}

class ChildOperation extends ParentOperation {
    @Override
    public void execute() {}
}
~~~

Đoạn này minh họa, không phải chương trình hoàn chỉnh. `@Deprecated` trên method của cha không tự trở thành annotation khai báo trên method override của con. `@Inherited` chỉ định ngữ nghĩa inheritance cho **annotation trên class**; không áp dụng cùng quy tắc cho method, field hay parameter.

Cần phân biệt **method overriding** (ngôn ngữ chọn phương thức thực thi) với **annotation inheritance trên class** (Reflection tra một loại metadata). Chúng là hai cơ chế khác nhau.

### 9.3. `@Documented` không quyết định ưu tiên annotation

`@Documented` khiến annotation có thể được đưa vào Javadoc của phần tử khai báo. Nó không tạo đường đi kế thừa và không định nghĩa cách class con che annotation. Trong chủ đề “tài liệu và kế thừa”, phải phân biệt:

- `@Documented`: ảnh hưởng cách annotation xuất hiện trong tài liệu API.
- `@Inherited`: ảnh hưởng quy tắc tra cứu annotation trên class khi class hiện tại chưa có annotation phù hợp.
- `@Retention(RUNTIME)`: ảnh hưởng việc Reflection có thể đọc annotation lúc chạy.

Để đọc chính xác annotation được giữ lại, phải xét đủ metadata, vị trí gắn và API truy vấn.

## 10. Trường hợp nâng cao: annotation có thể lặp

Khi annotation type được khai báo `@Repeatable`, mã Java có thể đặt nhiều annotation cùng kiểu trên một phần tử. Compiler có thể biểu diễn chúng qua **container annotation**; lúc này `getAnnotation(Tag.class)` không có cùng quy tắc “đọc hết” như `getAnnotationsByType(Tag.class)`.

Một cấu hình có thể lặp hợp lệ cần chú ý `@Inherited` cho chính annotation lặp **và** container tương ứng; nếu repeatable annotation có `@Inherited` thì container cũng phải phù hợp với yêu cầu kế thừa. Mẫu khái niệm:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("writer")
class BaseRoles {}

@Role("admin")
class ChildRoles extends BaseRoles {}
~~~

Ví dụ này là một đoạn khai báo hợp lệ, có thể dùng để quan sát các API Reflection.

Với `ChildRoles.class.getAnnotationsByType(Role.class)`, kết quả là annotation ở class con `admin`, **không tự động cộng thêm** `reader` và `writer` từ `BaseRoles`. Quy tắc associated annotation ưu tiên những annotation cùng loại hiện diện trực tiếp hoặc gián tiếp ngay tại class con trước khi tìm superclass.

Nếu `ChildRoles` không khai báo `Role` nào, `getAnnotationsByType(Role.class)` có thể trả các `Role` gắn ở superclass theo quy tắc `@Inherited`. Cần dùng `getAnnotationsByType` khi mục tiêu là đọc đầy đủ một annotation type lặp; `getAnnotation(Role.class)` có thể không trả phần tử mong đợi trong trường hợp các annotation được đóng gói vào container.

Không nhất thiết phải hiểu hết `@Repeatable` để nắm bài chính. Hãy giữ quy tắc cơ bản: việc class con khai báo cùng **loại annotation** có ảnh hưởng tới kết quả inheritance; với repeatable annotation, cách API xác định sự hiện diện còn phải xét container và phương thức tra cứu.

## 11. Các lỗi thường gặp

**Lỗi 1 — Quên `@Inherited`.** Đặt `@Mode` trên superclass, gọi `Child.class.getAnnotation(Mode.class)` rồi nhận `null`. Hãy kiểm tra annotation type có `@Inherited` không; `RUNTIME` một mình chưa đủ.

**Lỗi 2 — Đặt `@Inherited` nhưng quên `RUNTIME`.** `@Inherited` mô tả cơ chế inheritance, nhưng Reflection runtime không thấy annotation type có retention `CLASS`/`SOURCE`. Khi cần runtime reflection, khai báo rõ `@Retention(RUNTIME)`.

**Lỗi 3 — Tưởng các element được merge.** Class cha có `level = 7`, con ghi `@Mode("child")`, nhưng chương trình kỳ vọng `level = 7`. Kết quả Java là giá trị mặc định `1`; muốn merge phải tự lập quy tắc.

**Lỗi 4 — Nhầm `getDeclaredAnnotation` với `getAnnotation`.** `getDeclaredAnnotation` chỉ tìm khai báo trên đúng class, nên `NoTag` trả `null` mặc dù `getAnnotation` tìm ra annotation kế thừa.

**Lỗi 5 — Tưởng sửa metadata của superclass.** Annotation con che trong quá trình tra cứu không sửa `Base.class`, không ghi đè file class của `Base` và không khiến truy vấn chính superclass có kết quả khác.

**Lỗi 6 — Tưởng implement interface cũng nhận annotation.** `@Inherited` chỉ tìm superclass của class; interface annotation cần mã/framework tự xét nếu có nhu cầu.

**Lỗi 7 — Áp dụng cơ chế này lên method override.** Method của class con không tự kế thừa annotation trên method cùng tên của cha do `@Inherited`. Đọc `Method` trên từng class sẽ thấy metadata theo đúng khai báo và API sử dụng.

**Lỗi 8 — Hiểu “cùng kiểu” là “cùng tên”.** Hai annotation type khác package dù có simple name giống nhau vẫn là hai type khác nhau. Quy tắc xét đối tượng `Class<? extends Annotation>` tương ứng, không chỉ chuỗi tên hiển thị.

**Lỗi 9 — Bỏ qua trường hợp annotation lặp.** Khi type có `@Repeatable`, phép tra `getAnnotationsByType` có ngữ nghĩa đi qua container và kế thừa khác với truy vấn một annotation đơn. Chọn API theo loại annotation đang cần đọc.

## 12. Bài tập thực hành

1. **Không khai báo ở lớp con:** Chạy `InheritedShadowDemo`. Trước khi chạy, dự đoán `NoTag.class.getAnnotation(Mode.class)` và `getDeclaredAnnotation(Mode.class)`; giải thích vì sao hai kết quả khác nhau.
2. **Che annotation cha:** Đổi `@Mode("child")` thành `@Mode(value = "child", level = 9)` trên `Child`. Dự đoán và kiểm chứng `Child` lẫn `Grandchild` nhận giá trị nào.
3. **Gỡ annotation con:** Xóa `@Mode("child")` khỏi `Child` (giữ `extends Base`). Chạy lại và giải thích vì sao `Child`/`Grandchild` trở về nhận `base:7`.
4. **Bỏ `@Inherited`:** Bỏ meta-annotation đó trên `Mode`. Thêm kiểm tra `null` an toàn trước khi đọc giá trị; dự đoán cách `NoTag` và `Grandchild` thay đổi.
5. **Bỏ retention runtime:** Chuyển `Mode` sang `CLASS`. Dự đoán `getAnnotation(...)` và lý giải vì sao metadata có thể còn trong `.class` nhưng Reflection không thấy.
6. **Thêm kiểu khác:** Tạo thêm `@Team("backend")` có `@Inherited`, đặt trên `Base` và chỉ ghi đè `Mode` ở `Child`. So sánh hai truy vấn riêng: `getAnnotation(Mode.class)` và `getAnnotation(Team.class)` trên `Child`.
7. **Interface và member:** Gắn `@Mode` lên interface; thử một class `implements`. Tạo annotation `@Target(METHOD)` trên method cha rồi override method đó tại con, so sánh hai `Method.getDeclaredAnnotations()`.
8. **Repeatable:** Chạy đoạn `Role`/`Roles`, in `Arrays.toString(...)` hoặc duyệt `getAnnotationsByType(Role.class)` trên `ChildRoles`. Sau đó bỏ `@Role("admin")` ở con và kiểm chứng tính kế thừa.

## 13. Kết luận học tập

Annotation khai báo trực tiếp trên subclass **ưu tiên** trước annotation cùng kiểu có thể được kế thừa từ superclass. Nếu subclass không khai báo, `@Inherited` cho phép Reflection tìm lần lượt superclass gần nhất. Nếu subclass đã khai báo, giá trị của subclass là giá trị hiệu lực của annotation được tìm; các element bỏ qua lấy mặc định của annotation type, không ghép từ cha. `getDeclaredAnnotation` trả lời câu hỏi **ai khai báo trực tiếp**, còn `getAnnotation` trả lời câu hỏi **annotation nào được coi là hiện diện** theo quy tắc Java.

Để áp dụng chắc chắn, hãy kiểm tra type có `@Inherited` hay không, retention có cho runtime Reflection không, annotation được gắn trên loại phần tử nào và API truy vấn cụ thể là gì.

### Tài liệu tham khảo

- [Java Language Specification 17 — `9.6.4.3: `@Inherited`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3).
- [Java SE 17 API — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).
- [Java SE 17 API — `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
