# Giới hạn kế thừa và lỗi phụ thuộc vòng giữa các kiểu annotation trong Java

Một kiểu annotation Java được khai báo bằng `@interface`. Nó giống interface thường ở một số điểm, nhưng **không có cơ chế kế thừa `extends` tùy ý**, và các phần tử của nó phải có kiểu dữ liệu hợp lệ. Đặc biệt, Java **cấm một annotation chứa chính kiểu annotation đó trong chuỗi kiểu trả về của các element, trực tiếp hoặc gián tiếp**.

Chủ đề này có ba quan hệ dễ bị nhầm với nhau:

1. **Quan hệ kế thừa kiểu** (`extends`): annotation type không được khai báo cha bằng `extends` như interface thường.
2. **Quan hệ chứa dữ liệu**: annotation element có thể trả về kiểu annotation khác, nhưng chuỗi phụ thuộc qua các kiểu trả về **không được tạo vòng**.
3. **Quan hệ gắn annotation / kế thừa annotation trên class**: annotation có thể gắn lên annotation khác (meta-annotation); `@Inherited` có thể giúp một annotation được truy vấn từ subclass. Hai cơ chế này **không phải kế thừa kiểu annotation**.

Hiểu sự khác biệt giúp thiết kế metadata gọn, tránh lỗi biên dịch và không trông chờ Java tự gộp các annotation theo ý nghĩa của một framework.

## 1. Annotation type là interface đặc biệt, nhưng không có extends clause

Một annotation type được khai báo như sau:

```java
@interface Label {
    String value();
}
```

Đây là **khai báo kiểu annotation hợp lệ**. Phần tử `value()` mô tả dữ liệu bắt buộc người dùng annotation phải cung cấp (trừ khi có giá trị `default`). Nó không phải một method tùy ý có thân thực thi.

Java quy định superinterface trực tiếp của **mọi annotation type** luôn là `java.lang.annotation.Annotation`. Quan hệ này được ngôn ngữ thiết lập ngầm; lập trình viên **không được chọn superinterface bằng `extends`**.

Ví dụ sai, cố ý **không biên dịch được**:

```java
@interface ParentTag {
    String value();
}

// SAI: cú pháp @interface không cho phép extends.
@interface ChildTag extends ParentTag {
    int version();
}
```

Khi chuyển từ interface thông thường sang annotation, đừng mang theo trực giác sau:

```java
interface Parent {
    void doWork();
}

// ĐÚNG với interface thông thường.
interface Child extends Parent {
    void doMore();
}
```

Hai đoạn thể hiện sự khác biệt về cú pháp: `interface Child extends Parent` được phép đối với interface thường; `@interface ChildTag extends ParentTag` không hợp lệ.

**Hệ quả:**

- Không có cách tạo `@AdminRole` “kế thừa toàn bộ element” của `@Role` bằng `extends`.
- Không thể trông chờ annotation mới tự kế thừa `value()`, `level()`, `default` hoặc các meta-annotation đã gắn trên annotation khác.
- Có thể tổ chức annotation theo **cấu thành (composition)** hoặc metadata bổ trợ, nhưng chương trình/công cụ sử dụng phải hiểu và xử lý quan hệ ấy.

Một điều tinh tế: vì `@interface` là một loại interface, Java cho nó những phương thức do `java.lang.annotation.Annotation` định nghĩa, chẳng hạn `annotationType()`. Tuy nhiên, những phương thức thừa hưởng này **không trở thành các annotation element do bạn khai báo**.

## 2. Annotation element được phép có kiểu nào?

Trong phần thân `@interface`, các method khai báo element có kiểu trả về bị giới hạn. Java cho phép:

| Nhóm kiểu | Ví dụ element hợp lệ |
| --- | --- |
| Kiểu nguyên thủy | `int level();`, `boolean enabled();` |
| `String` | `String name();` |
| `Class` hoặc kiểu `Class` với generic hợp lệ | `Class<?> target();` |
| Một kiểu enum | `Mode mode();` nếu `Mode` là enum |
| Một kiểu annotation khác | `Details details();` |
| Mảng một chiều của các kiểu hợp lệ phía trên | `String[] tags();`, `Details[] items();` |

Ví dụ một cấu trúc hợp lệ:

```java
enum Priority {
    LOW, HIGH
}

@interface Details {
    String author();
    int revision() default 1;
}

@interface Definition {
    String name();
    Priority priority() default Priority.LOW;
    Details details();
    Class<?> owner();
    String[] aliases() default {};
}
```

Đây là **các khai báo kiểu độc lập về logic**, không có method `main`. `Definition` phụ thuộc một chiều vào `Details`, vì element `details()` trả về annotation type `Details`.

Các khai báo sau **sai và không được đưa vào chương trình chạy**:

```java
@interface Invalid {
    Object object();         // SAI: Object không phải kiểu element hợp lệ.
    java.util.List<String> names(); // SAI: List<String> không hợp lệ.
    String[][] matrix();     // SAI: mảng hai chiều.
    void run();              // SAI: void không phải kiểu element hợp lệ.
}
```

Java còn giới hạn chữ ký element: method không có tham số, không có type parameter và `throws`, không được định nghĩa body như method instance thường. Lỗi phụ thuộc vòng là một quy tắc bổ sung bên cạnh giới hạn về kiểu trả về.

## 3. Lỗi phụ thuộc vòng trực tiếp: annotation trả về chính nó

Xem khai báo cố ý sai:

```java
@interface SelfRef {
    SelfRef value();  // SAI: kiểu element là chính annotation chứa nó.
}
```

Mô hình phụ thuộc có vòng:

```text
SelfRef
   └── value(): SelfRef
             └── quay lại SelfRef
```

Trình biên dịch báo lỗi vì kiểu annotation `SelfRef` chứa một element có kiểu `SelfRef`.

Đổi từ đối tượng đơn sang mảng **không phá vòng**:

```java
@interface TreeNode {
    TreeNode[] children();  // VẪN SAI: thành phần mảng là TreeNode.
}
```

Một số người liên tưởng tới class Java có thể tự tham chiếu, chẳng hạn:

```java
class Node {
    Node next; // Hợp lệ với class Java thông thường.
}
```

Suy luận ấy không áp dụng được nguyên trạng cho `@interface`. Class có tham chiếu object linh hoạt khi chương trình chạy; annotation element phải thuộc mô hình giá trị metadata hữu hạn và tuân thủ quy tắc vòng của Java Language Specification (JLS §9.6.1).

## 4. Lỗi phụ thuộc vòng gián tiếp: A → B → A

Java cũng cấm **vòng đi qua nhiều kiểu annotation**, ngay cả khi mỗi khai báo chỉ nhắc tới một kiểu khác:

```java
@interface Ping {
    Pong value();
}

@interface Pong {
    Ping value();
}
```

Đây là **ví dụ cố ý gây compile-time error**, không phải chương trình chạy được. Vòng phụ thuộc:

```text
Ping.value(): Pong
      ↓
Pong.value(): Ping
      ↓
quay lại Ping
```

Trường hợp dài hơn vẫn sai:

```java
@interface A {
    B b();
}

@interface B {
    C[] c();
}

@interface C {
    A parent();
}
```

Dù `B.c()` trả về `C[]`, cạnh phụ thuộc vẫn là từ `B` tới `C`. Kết quả là `A → B → C → A`.

### Quy tắc để tự kiểm tra

Chỉ xét quan hệ **một annotation element có kiểu trả về là annotation type khác**, hoặc mảng của annotation type khác. Biểu diễn như đồ thị có hướng:

- Mỗi annotation type là một đỉnh.
- `@interface X { Y item(); }` tạo cạnh `X → Y`.
- `@interface X { Y[] items(); }` cũng tạo cạnh `X → Y`.
- Nếu đi theo những cạnh đó rồi quay lại một đỉnh đã gặp, **có chu trình bị cấm**.
- Nếu không có chu trình, quan hệ chứa giữa các annotation type có thể hợp lệ, miễn là những quy tắc khai báo và sử dụng khác cũng được đáp ứng.

Ví dụ cấu thành không vòng:

```text
RequestMeta
    ├── OwnerInfo
    └── AuditInfo
             └── AuditFlags

Không có cạnh nào quay về RequestMeta.
```

Cách nghĩ theo đồ thị giúp phát hiện vòng dài qua nhiều lớp metadata, kể cả khi mỗi `@interface` nằm ở một tệp riêng.

## 5. Đừng nhầm vòng của element với vòng meta-annotation

**Điểm rất quan trọng:** Java **cho phép** một annotation type được gắn bằng một annotation type khác, và thậm chí có thể xuất hiện vòng trong quan hệ *gắn annotation lên khai báo annotation*. Quy tắc cấm vòng ở §9.6.1 là **vòng kiểu trả về của element**, không phải mọi quan hệ có dạng mũi tên giữa các annotation.

Ví dụ hợp lệ về quan hệ meta-annotation, trình bày như các khai báo cùng phạm vi package:

```java
@Right
@interface Left {}

@Left
@interface Right {}
```

Ở đây:

- `@Right` được **gắn lên khai báo** `Left`.
- `@Left` được **gắn lên khai báo** `Right`.
- Không annotation nào khai báo element trả về kiểu annotation kia.

Theo JLS §9.7.1, quan hệ “annotation type A annotate khai báo annotation type B” có thể tạo vòng. **Không nên áp quy tắc cấm vòng element sang vòng meta-annotation**.

Tuy nhiên, một số framework có thể tự duyệt meta-annotation theo kiểu đệ quy; lúc đó vòng meta-annotation phải được **công cụ xử lý** bằng tập các kiểu đã duyệt, hoặc quy tắc dừng phù hợp. Đó là bài toán của công cụ đang đọc metadata, không phải lỗi vòng element mà `javac` bắt buộc từ chối.

### Meta-annotation không đồng nghĩa với kế thừa element hay tự động “truyền” metadata

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Secured {
    String role();
}

@Secured(role = "ADMIN")
@Retention(RetentionPolicy.RUNTIME)
@interface AdminOnly {}

@AdminOnly
class Dashboard {}
```

Đây là **khai báo minh họa**, chưa có `main`. Annotation `Secured` được gắn lên **kiểu annotation `AdminOnly`**. `Dashboard` được gắn trực tiếp `AdminOnly`, **không được gắn trực tiếp `Secured`**.

Vì vậy, reflection Java thuần túy:

```java
// Với các khai báo ở trên:
Dashboard.class.getAnnotation(Secured.class); // null
AdminOnly.class.getAnnotation(Secured.class); // trả về annotation Secured
```

Hai câu lệnh phía trên là **biểu thức minh họa**, không phải chương trình độc lập. Một framework có thể chủ động duyệt sâu các meta-annotation để hiểu `@AdminOnly` như “role=ADMIN”, nhưng Java reflection không tự suy ra `Secured` có mặt trực tiếp trên `Dashboard`.

## 6. @Inherited: kế thừa annotation trên class không phải kế thừa kiểu annotation

Tên `@Inherited` dễ tạo ấn tượng annotation type có thể `extends` nhau. Thực tế nó là **meta-annotation chuẩn** gắn trên định nghĩa một annotation type, tác động tới quá trình Java reflection **tìm annotation trên class qua chuỗi superclass**.

Ví dụ:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Access {
    String role();
}

@Access(role = "USER")
class BaseController {}

class AccountController extends BaseController {}
```

`AccountController.class.getAnnotation(Access.class)` có thể tìm thấy `@Access` từ `BaseController` vì có `@Inherited` và annotation được giữ tới runtime.

**Giới hạn cần nhớ:**

- `@Inherited` làm việc khi annotation **được truy vấn trên khai báo class**; nó không tạo thêm `extends` trong khai báo annotation type.
- Chỉ tra cứu qua **superclass**, không thông qua interface mà class `implements`.
- Không làm annotation trên **method, field, parameter** tự động được thừa hưởng theo quan hệ override/kế thừa thành viên.
- `Class.getAnnotation(...)` có thể trả về annotation kế thừa; `Class.getDeclaredAnnotation(...)` chỉ đọc annotation khai báo trực tiếp trên class đang xét.
- Nếu subclass khai báo chính annotation type đó, annotation khai báo trực tiếp được ưu tiên khi tra cứu.

Đây là điều khác với giới hạn **kiểu trả về của annotation element** tại JLS §9.6.1. Một định nghĩa `@Inherited` không thể hợp thức hóa khai báo vòng `@interface Node { Node next(); }`.

## 7. Ví dụ Java 17+ độc lập: cấu thành hợp lệ và quan sát @Inherited

Tạo đúng một tệp **`AnnotationBoundariesDemo.java`** với nội dung sau. Tất cả kiểu cần thiết đều nằm trong tệp, có đúng một class `public` trùng tên tệp. Ví dụ này minh họa:

- **Cấu thành một chiều**: `@Feature` chứa element kiểu `Detail`.
- **Không có vòng element** nên biên dịch được.
- Một annotation có `@Inherited` và annotation khác không có `@Inherited`.
- Sự khác biệt giữa `getAnnotation` và `getDeclaredAnnotation`.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Hint {
    String value();
}

// Chỉ dùng dưới dạng giá trị lồng của annotation khác.
@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Detail {
    String name();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Feature {
    Detail detail(); // Cạnh Feature -> Detail, không quay lại Feature.
}

@Role("base")
@Hint("direct")
class Parent {}

class Child extends Parent {}

@Feature(detail = @Detail(name = "audit"))
class Service {}

public class AnnotationBoundariesDemo {
    public static void main(String[] args) {
        Role inherited = Child.class.getAnnotation(Role.class);
        System.out.println(inherited.value());

        Role declared = Child.class.getDeclaredAnnotation(Role.class);
        System.out.println(declared == null);

        Hint notInherited = Child.class.getAnnotation(Hint.class);
        System.out.println(notInherited == null);

        Feature feature = Service.class.getAnnotation(Feature.class);
        System.out.println(feature.detail().name());
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 AnnotationBoundariesDemo.java
java AnnotationBoundariesDemo
```

Stdout chính xác của `java AnnotationBoundariesDemo`:

```text
base
true
true
audit
```

Diễn giải:

1. `base`: `Child` kế thừa class `Parent`, và `Role` có `@Inherited`. Phép tra `getAnnotation(Role.class)` nhìn lên superclass.
2. `true` (dòng hai): `Child` không **trực tiếp** khai báo `@Role`, nên `getDeclaredAnnotation(Role.class)` trả về `null`.
3. `true` (dòng ba): `Hint` không có `@Inherited`, vì vậy `Child.class.getAnnotation(Hint.class)` trả về `null` mặc dù `Parent` có `@Hint`.
4. `audit`: `Feature.detail()` chứa một giá trị annotation kiểu `Detail`, và có thể được truy xuất hợp lệ tại runtime nhờ `@Retention(RUNTIME)`.

Lưu ý: `@Target({})` được dùng cho `Detail` nhằm hướng annotation đó vào vai trò **giá trị lồng**, không gắn trực tiếp lên class/method. Đây là lựa chọn thiết kế; nó không làm `Feature → Detail` biến thành quan hệ kế thừa.

### So sánh code hợp lệ và code lỗi

| Tình huống | Kết quả | Lý do |
| --- | --- | --- |
| `@interface A { String value(); }` | Hợp lệ | Kiểu element là `String` |
| `@interface A { B value(); }`; `@interface B { String name(); }` | Hợp lệ | Phụ thuộc một chiều `A → B` |
| `@interface A { A value(); }` | Compile-time error | Tự tham chiếu element trực tiếp |
| `@interface A { B value(); }`; `@interface B { A value(); }` | Compile-time error | Vòng element gián tiếp |
| `@interface B extends A {}` | Không hợp lệ | Khai báo annotation type không có `extends` |
| `@B @interface A {}`; `@A @interface B {}` | Hợp lệ về quy tắc vòng element | Đây là vòng quan hệ meta-annotation, không phải element type |
| `@Inherited` trên kiểu `A` | Hợp lệ nếu áp dụng đúng target | Điều khiển tra cứu annotation trên subclass, không thừa kế element |

## 8. Một trường hợp thực tế liên quan: @Repeatable và annotation chứa

Java hỗ trợ dùng lặp một annotation thông qua `@Repeatable`. Cơ chế này cần một **container annotation** có element `value()` trả về mảng của annotation được lặp.

Ví dụ khai báo hợp lệ:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@interface Tags {
    Tag[] value();
}
```

Tại đây có quan hệ element **`Tags → Tag`**, trong khi `@Repeatable(Tags.class)` là metadata gắn lên khai báo `Tag`. Điều đó **không tự tạo cạnh element `Tag → Tags`**, vì `Tag` không khai báo method trả về `Tags`.

Thêm một element như sau vào `Tag` sẽ làm hình thành chu trình kiểu trả về và bị từ chối:

```java
// Minh họa SAI: các định nghĩa sau tạo vòng element.
@Repeatable(Tags.class)
@interface Tag {
    Tags parent(); // Tag -> Tags
}

@interface Tags {
    Tag[] value(); // Tags -> Tag
}
```

Đoạn trên cố ý **không biên dịch được**; nếu giữ khai báo container ban đầu và không thêm element `parent()`, cấu trúc `@Repeatable` có thể hợp lệ. Để dùng annotation lặp trong dự án thật, còn phải đáp ứng các điều kiện khác về retention, target, và các element của container theo JLS §9.6.3.

Trường hợp này cho thấy tại sao không thể kết luận “cứ hai annotation có nhắc tên nhau là lỗi vòng”. **Quan trọng là quan hệ nào tạo cạnh thông qua kiểu trả về element.**

## 9. Thiết kế lại annotation khi gặp lỗi vòng

Giả sử một hệ thống muốn mô tả luồng công việc bằng metadata, và thiết kế ban đầu vô tình tạo vòng:

```java
// SAI: hai kiểu chứa trực tiếp/gián tiếp lẫn nhau.
@interface Workflow {
    Step[] steps();
}

@interface Step {
    Workflow parent();
}
```

Có thể khắc phục bằng cách **giữ quan hệ một chiều** nếu bài toán chỉ cần phân nhóm:

```java
@interface Step {
    String name();
}

@interface Workflow {
    Step[] steps();
}

@Workflow(steps = {
    @Step(name = "validate"),
    @Step(name = "persist")
})
class OrderWorkflow {}
```

Đoạn thứ hai là các khai báo sử dụng annotation **hợp lệ** (chưa có `main`). Mỗi `Step` chỉ mang dữ liệu đơn giản; `Workflow` gom các bước. Tránh đưa `Workflow` ngược vào `Step`.

Nếu thực sự cần “liên kết ngược”, có thể lưu một mã định danh, ví dụ `String workflowId()`, rồi để code xử lý mapping ngoài annotation. Với cấu trúc cây, đồ thị động hoặc dữ liệu tự tham chiếu, object model thông thường có thể phù hợp hơn annotation metadata.

**Đừng đổi thành `Class<?>` chỉ để lách quy tắc rồi mặc định rằng Java sẽ kiểm tra toàn bộ quan hệ nghiệp vụ giúp bạn.** `Class<?>` là kiểu element hợp lệ, nhưng việc kiểm tra một class token có trỏ tới loại mong muốn hay không và xử lý chu trình logic vẫn thuộc code tiêu thụ metadata.

### Kiểm tra lỗi theo trình tự

1. Đọc chính xác lỗi của `javac` và tìm element khai báo kiểu trả về annotation.
2. Vẽ các cạnh phụ thuộc `A → B` từ method element, bao gồm phần tử kiểu mảng.
3. Xác định vòng có quay lại cùng annotation type không.
4. Xác định quan hệ nào thực sự cần lưu ở cả hai chiều. Nếu không cần, bỏ cạnh quay lại hoặc thay bằng dữ liệu định danh.
5. Giữ đúng các kiểu element được JLS cho phép; tránh `Object`, `List`, mảng nhiều chiều.
6. Nếu các annotation chỉ **gắn lên nhau** mà không có element vòng, kiểm tra consumer/framework để xác định vòng metadata có được xử lý an toàn không. Không quy ngay lỗi cho `@interface`.

## 10. Những nhầm lẫn thường gặp

**“Annotation type là interface, nên `@interface B extends A` hẳn phải hợp lệ.”** Sai. Cú pháp annotation type không cho `extends`, dù nó có superinterface ngầm `Annotation`.

**“`@Inherited` cho phép annotation con thừa kế element từ annotation cha.”** Sai. `@Inherited` ảnh hưởng đến cách reflection tra cứu annotation qua superclass khi annotation được gắn lên class.

**“Annotation chứa annotation khác là lỗi.”** Sai. `@interface A { B b(); }` hợp lệ khi `B` được khai báo hợp lệ và không có đường phụ thuộc quay lại `A`.

**“Dùng `A[]` thay `A` là hết tự tham chiếu.”** Sai. Mảng vẫn chứa kiểu annotation `A` và tạo vòng tương ứng.

**“Hai annotation gắn lên nhau là chắc chắn lỗi biên dịch.”** Sai. Meta-annotation có thể tạo vòng mà không vi phạm quy tắc cấm vòng element. Tuy nhiên, consumer đệ quy metadata cần tự có cơ chế dừng.

**“Một annotation được meta-annotate bằng annotation khác thì mọi class dùng nó tự mang annotation kia.”** Sai đối với reflection Java thuần túy. Muốn diễn giải quan hệ tổng hợp đó cần consumer phù hợp.

**“`@Repeatable` tự tạo lỗi vòng vì container tham chiếu annotation được lặp.”** Sai. Chỉ có element container trả về annotation được lặp; bản thân thuộc tính `@Repeatable` không phải element trả về container.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `@interface B extends A {}` lỗi, còn `interface B extends A {}` có thể hợp lệ?

**Đáp án:** `@interface` có cú pháp riêng, không có `extends` và luôn có superinterface `java.lang.annotation.Annotation` do ngôn ngữ định nghĩa. Interface thông thường được phép chỉ định superinterface.

**Câu 2.** Phụ thuộc `Header → Footer → Header` qua các element trả về có được Java chấp nhận không?

**Đáp án:** Không. Đó là vòng gián tiếp trong các kiểu element của annotation.

**Câu 3.** `@interface Tree { Tree[] children(); }` có hợp lệ vì dùng mảng không?

**Đáp án:** Không. Phần tử mảng vẫn là `Tree`, tạo tự tham chiếu.

**Câu 4.** Vì sao `@A @interface B {}` và `@B @interface A {}` không nhất thiết là lỗi vòng element?

**Đáp án:** Vì đó là quan hệ annotation được gắn vào khai báo annotation khác; không có element nào bắt buộc trả về chính kiểu kia.

**Câu 5.** `@Inherited` có áp dụng cho annotation trên interface và method override theo cách tự động không?

**Đáp án:** Không. Nó áp dụng cho việc tra cứu annotation trên class qua chuỗi superclass.

**Câu 6.** Khi cần một annotation `@Workflow` chứa nhiều `@Step`, nhưng cũng cần thông tin workflow từ mỗi step, nên bắt đầu sửa thiết kế thế nào?

**Đáp án:** Giữ chiều `Workflow → Step` ở element và truyền khóa định danh hoặc xử lý quan hệ ngược ở logic riêng, tránh `Step → Workflow` bằng annotation element.

## Tài liệu chính thức

- [Java Language Specification 17, §9.6 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6).
- [JLS 17, §9.6.1 — Annotation Interface Elements và cấm tự tham chiếu](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1).
- [JLS 17, §9.7.1 — Quan hệ meta-annotation có thể tạo vòng](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1).
- [Java 17 API: java.lang.annotation.Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).

Khi review một thiết kế annotation, hãy phân biệt **kế thừa kiểu**, **phụ thuộc qua element** và **quan hệ gắn annotation**. Java giới hạn từng quan hệ theo những quy tắc khác nhau; việc phân biệt chính xác sẽ giúp đọc lỗi compiler và chọn thiết kế metadata hợp lý.
