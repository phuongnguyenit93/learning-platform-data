# @Inherited và việc tra cứu annotation qua lớp cha trong Java

Một annotation gắn trên lớp cha **có thể được tìm thấy khi truy vấn annotation trên lớp con** nếu kiểu annotation đó được đánh dấu bằng meta-annotation **@Inherited**. Java áp dụng quy tắc này khi tra cứu annotation trên **khai báo class**, đi lần lượt qua chuỗi superclass nếu class đang xét không khai báo trực tiếp annotation tương ứng.

Điều quan trọng là **@Inherited không sao chép annotation vào class con** và cũng không có nghĩa mọi annotation trên class, method, field hay interface đều được kế thừa. Đây là quy tắc về sự hiện diện của annotation trong quá trình tra cứu, đặc biệt dễ nhận thấy qua API reflection.

## 1. Cách khai báo một annotation được kế thừa

**@Inherited** nằm trong package **java.lang.annotation** và được gắn lên **khai báo kiểu annotation**, không gắn trực tiếp lên lớp con.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Configuration {
    String value();
}
~~~

Mỗi meta-annotation có nhiệm vụ riêng:

- **@Inherited** cho phép quy tắc tìm annotation trên superclass khi class con không khai báo trực tiếp annotation cùng kiểu.
- **@Retention(RetentionPolicy.RUNTIME)** giữ metadata để truy vấn được từ reflection lúc chạy. Nếu không chỉ định retention, mặc định là **CLASS**; khi đó không thể mong chờ **Class.getAnnotation(...)** tìm thấy annotation qua reflection.
- **@Target(ElementType.TYPE)** giới hạn vị trí dùng Configuration vào khai báo kiểu như class, interface, enum hoặc annotation type. Việc có thể *đặt* một annotation lên interface không đồng nghĩa annotation ấy được truyền từ interface sang class triển khai.
- **String value()** là phần tử của Configuration. Tên **value** cho phép viết rút gọn **@Configuration("prod")** thay cho **@Configuration(value = "prod")**.

Ví dụ sử dụng:

~~~java
@Configuration("production")
class BaseService {
}

class OrderService extends BaseService {
}
~~~

Một lời gọi sau có thể tìm ra Configuration từ BaseService khi tra cứu trên OrderService:

~~~java
Configuration config =
        OrderService.class.getAnnotation(Configuration.class);
System.out.println(config.value()); // production
~~~

Đoạn truy vấn trên giả định kiểu Configuration có runtime retention và BaseService được gắn trực tiếp annotation như ví dụ. Trong mã thực tế, **getAnnotation(...)** có thể trả về **null**, nên cần kiểm tra trước khi gọi **value()**.

## 2. Quy tắc tra cứu trong chuỗi superclass

Với kiểu annotation **A** có **@Inherited**, khi truy vấn **SomeClass.class.getAnnotation(A.class)**, có thể hiểu theo thứ tự:

1. Kiểm tra class được hỏi có annotation kiểu **A** trực tiếp trên khai báo của nó hay không. Nếu có, sử dụng annotation đó.
2. Nếu không có và A mang **@Inherited**, kiểm tra **superclass trực tiếp**.
3. Nếu superclass cũng không khai báo trực tiếp A, tiếp tục đi lên chuỗi lớp cha.
4. Dừng khi tìm thấy một annotation phù hợp; nếu đi hết đến **Object** mà không tìm thấy, kết quả là **null**.

Ví dụ:

~~~text
@Policy("root")
class Root
    │
    └── class Intermediate extends Root
              │
              └── class FinalChild extends Intermediate
~~~

Giả sử Policy là annotation có **@Inherited** và **RUNTIME**. Khi truy vấn **FinalChild.class.getAnnotation(Policy.class)**, Java có thể tìm thấy Policy từ Root sau khi đi qua Intermediate. Không bắt buộc mỗi lớp trung gian phải khai báo lại annotation.

**Chỉ các lớp cha trong chuỗi extends được xét.** Một class có thể implements nhiều interface, nhưng Java không tìm @Inherited từ danh sách interface để trả về annotation cho class triển khai.

### Class con khai báo lại cùng annotation

~~~java
@Policy("root")
class Root {
}

@Policy("child")
class Specialized extends Root {
}
~~~

Khi tra cứu Policy trên Specialized, kết quả là **"child"**. Annotation trực tiếp ở class con được ưu tiên, nên không tiếp tục lấy bản trên Root cho cùng kiểu annotation. Hai bản này không được tự gộp các phần tử với nhau.

Ví dụ nếu Policy có các phần tử **name()** và **active() default true**, lớp con tự khai báo **@Policy(name = "child")** thì **active()** nhận default của *kiểu Policy*, chứ không kế thừa một giá trị **active = false** mà lớp cha có thể đã khai báo tường minh trong annotation của lớp cha.

## 3. @Inherited khác việc kế thừa class, method và field

Kế thừa hành vi qua **extends** là cơ chế của hệ thống kiểu và phương thức trong Java. Kế thừa annotation theo **@Inherited** là một quy tắc tra cứu metadata trên **class**.

| Tình huống | Annotation tự được tìm qua @Inherited? | Giải thích |
| --- | --- | --- |
| Class B extends A, A có **@Policy** và Policy có **@Inherited** | Có | Truy vấn class B có thể đi lên superclass A |
| Class C extends B extends A | Có, nếu không bị bản trực tiếp ở lớp gần hơn che | Tra cứu tiếp qua chuỗi superclass |
| B tự có **@Policy** | Dùng bản B | Annotation trực tiếp trên B được ưu tiên |
| Class B implements interface I được gắn **@Policy** | Không | @Inherited không đi theo quan hệ implements |
| Interface J extends interface I được gắn **@Policy** | Không theo cơ chế @Inherited | Chỉ có quy tắc tra cứu trên superclass của class |
| Method ở lớp con override method có annotation trên lớp cha | Không | @Inherited không sao chép annotation sang method override |
| Field trong lớp cha có annotation và lớp con khai báo field mới cùng tên | Không | @Inherited không truyền annotation từ field này sang field khác |
| Kiểu annotation thiếu **@Inherited** | Không | Class con không tự có annotation nếu không khai báo trực tiếp |

Chẳng hạn, đoạn sau minh họa rõ giới hạn đối với method:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Logged {
}

class Parent {
    @Logged
    public void execute() {
    }
}

class Child extends Parent {
    @Override
    public void execute() {
    }
}
~~~

Dù **Logged** mang @Inherited, câu lệnh **Child.class.getDeclaredMethod("execute").getAnnotation(Logged.class)** trả về **null**. Cơ chế @Inherited chỉ có tác dụng khi một annotation được dùng để chú thích **class**, không áp dụng để truyền annotation qua chuỗi override của method. Ngược lại, annotation **@Override** trên execute của Child là kiểm tra đúng hành vi override tại compile time, không liên quan tới việc kế thừa Logged.

**Một trường hợp dễ gây nhầm:** nếu Child *không override* execute, **Child.class.getMethod("execute")** có thể trả về đối tượng **Method** thuộc khai báo của Parent. Khi đọc Logged trên Method đó, có thể thấy annotation của Parent vì bạn đang quan sát chính method khai báo ở Parent. Đó **không phải** hiệu ứng @Inherited áp dụng lên method của Child.

## 4. getAnnotation và getDeclaredAnnotation khác nhau thế nào?

Khi sử dụng **Class** reflection, hai phương thức này giải quyết hai câu hỏi khác nhau:

~~~java
Configuration effective =
        Child.class.getAnnotation(Configuration.class);

Configuration local =
        Child.class.getDeclaredAnnotation(Configuration.class);
~~~

- **getAnnotation(...)**: tìm annotation của kiểu được yêu cầu **đang hiện diện (present)** trên class. Với annotation được @Inherited, kết quả có thể đến từ superclass.
- **getDeclaredAnnotation(...)**: chỉ tìm annotation **khai báo trực tiếp** trên class được hỏi, bỏ qua mọi annotation tìm thấy theo cơ chế kế thừa.
- **isAnnotationPresent(...)**: trả boolean cho việc annotation kiểu đó hiện diện theo cùng ý tưởng tra cứu của **getAnnotation(...)**.
- **getAnnotations()**: trả mảng các annotation hiện diện trên class, trong đó có thể có annotation inherited từ superclass nếu kiểu cho phép.
- **getDeclaredAnnotations()**: chỉ trả những annotation khai báo trực tiếp trên class, không gồm bản inherited.

Bảng đối chiếu khi **@Configuration** có @Inherited:

| Class | getAnnotation(Configuration.class) | getDeclaredAnnotation(Configuration.class) |
| --- | --- | --- |
| **BaseService** có @Configuration | Có | Có |
| **OrderService extends BaseService**, không gắn Configuration | Có, nhận bản từ BaseService | null |
| **IndependentService** không gắn và không kế thừa lớp có Configuration | null | null |
| **CustomService extends BaseService** có @Configuration riêng | Có, nhận bản trực tiếp từ CustomService | Có |

Từ Java 8 trở đi còn có **getAnnotationsByType(...)** và **getDeclaredAnnotationsByType(...)** để làm việc với annotation lặp lại (*repeatable annotation*). Các API này hỗ trợ tìm annotation có thể được chứa gián tiếp trong container; chúng khác với API đơn lẻ ở cách xử lý repeatable annotation. Khi bài toán yêu cầu nhiều annotation cùng kiểu, nên dùng API *ByType* và đọc thêm quy tắc @Repeatable thay vì suy luận chỉ từ getAnnotation.

## 5. Ví dụ Java 17+ chạy độc lập: kế thừa, che khuất và interface

Tạo tệp **src/demo/InheritedLookupDemo.java**:

~~~java
package demo;

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
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalOnly {
}

@Mode("base")
@LocalOnly
class Base {
}

class Middle extends Base {
}

class Leaf extends Middle {
}

@Mode("override")
class Overridden extends Base {
}

@Mode("interface")
interface Contract {
}

class ContractImpl implements Contract {
}

public class InheritedLookupDemo {
    public static void main(String[] args) {
        inspect(Base.class);
        inspect(Middle.class);
        inspect(Leaf.class);
        inspect(Overridden.class);
        inspect(Contract.class);
        inspect(ContractImpl.class);
    }

    private static void inspect(Class<?> type) {
        Mode effective = type.getAnnotation(Mode.class);
        Mode declared = type.getDeclaredAnnotation(Mode.class);
        LocalOnly local = type.getAnnotation(LocalOnly.class);

        String mode = effective == null
                ? "<none>" : effective.value();

        System.out.println(type.getSimpleName()
                + ": mode=" + mode
                + ", declaredMode=" + (declared != null)
                + ", localOnly=" + (local != null));
    }
}
~~~

Từ thư mục chứa **src**, biên dịch và chạy:

~~~bash
javac -encoding UTF-8 -d out src/demo/InheritedLookupDemo.java
java -cp out demo.InheritedLookupDemo
~~~

Stdout:

~~~text
Base: mode=base, declaredMode=true, localOnly=true
Middle: mode=base, declaredMode=false, localOnly=false
Leaf: mode=base, declaredMode=false, localOnly=false
Overridden: mode=override, declaredMode=true, localOnly=false
Contract: mode=interface, declaredMode=true, localOnly=false
ContractImpl: mode=<none>, declaredMode=false, localOnly=false
~~~

**Phân tích kết quả:**

1. **Base** khai báo trực tiếp **@Mode("base")** và **@LocalOnly** nên các kiểm tra tương ứng đều true.
2. **Middle** và **Leaf** không khai báo trực tiếp Mode nhưng **getAnnotation(Mode.class)** tìm được Mode từ Base, vì Mode có @Inherited. Do đó **declaredMode** vẫn false trên hai class.
3. **LocalOnly** không có @Inherited, nên các class con không nhận được LocalOnly qua tra cứu reflection của class.
4. **Overridden** có **@Mode("override")** trực tiếp, vì vậy nhận "override" và không nhận "base" từ Base cho cùng kiểu Mode.
5. **Contract** là interface có gắn Mode trực tiếp. Truy vấn trên bản thân **Contract.class** thấy Mode của Contract vì nó có metadata trực tiếp.
6. **ContractImpl** triển khai Contract nhưng không nhận Mode từ Contract: implements không nằm trong cơ chế @Inherited.

Cả Mode và LocalOnly có **@Retention(RUNTIME)**, nên kết quả được truy xuất qua reflection. **@Target(TYPE)** cho phép gắn annotation lên class và interface, nhưng nó không thay đổi quy tắc thừa kế.

**Lưu ý về tệp nguồn:** ví dụ sử dụng các annotation và class phụ không public trong cùng package **demo**; chỉ có **InheritedLookupDemo** là public, do đó toàn bộ đoạn mã biên dịch trong một tệp có cùng tên public class.

## 6. @Inherited có sao chép annotation vào class con không?

Không. Hãy phân biệt:

- **Annotation khai báo trực tiếp (directly present):** được viết lên chính class, chẳng hạn **@Mode("base") class Base**.
- **Annotation có thể được kế thừa (present through inheritance):** khi truy vấn class con, reflection tìm trong chuỗi superclass vì kiểu annotation có **@Inherited**.
- **Annotation tự ghi lại vào class file con:** đây **không phải** điều @Inherited thực hiện. Class con không tự được biên dịch lại hoặc thêm annotation vào phần khai báo trực tiếp chỉ vì class cha mang annotation.

Có thể đối chiếu bằng lệnh **javap**:

~~~bash
javap -v -p out/demo/Base.class
javap -v -p out/demo/Middle.class
~~~

Với retention RUNTIME, **Base.class** có metadata về Mode và LocalOnly. **Middle.class** không cần chứa bản copy trực tiếp của Mode để **Middle.class.getAnnotation(Mode.class)** vẫn trả được annotation của Base.

Điều này cũng giải thích vì sao **getDeclaredAnnotation(Mode.class)** trên Middle trả về null, còn **getAnnotation(Mode.class)** tìm được Mode từ Base. Muốn kiểm tra nơi nào **tự khai báo annotation**, chọn API có **Declared**; muốn kiểm tra giá trị annotation **hiệu lực trong quá trình tra cứu class**, chọn API thông thường.

### Giá trị của annotation nhận từ lớp cha

Khi một annotation được tìm từ superclass, các phần tử của nó giữ ý nghĩa như annotation khai báo ở lớp nguồn; Java không tự ghi đè từng phần tử theo cấu hình của lớp con.

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Access {
    String role();
    boolean enabled() default true;
}

@Access(role = "reader", enabled = false)
class ParentArea {
}

class ChildArea extends ParentArea {
}

@Access(role = "writer")
class WriterArea extends ParentArea {
}
~~~

Với **ChildArea**, việc gọi **getAnnotation(Access.class)** nhận Access từ ParentArea, cho **role() = "reader"** và **enabled() = false**. Với **WriterArea**, Access được khai báo trực tiếp và cho **role() = "writer"**, **enabled() = true** do default của kiểu Access. Giá trị **enabled = false** của ParentArea không được tự trộn vào Access trên WriterArea.

Nếu thư viện cần cơ chế gộp cấu hình của nhiều cấp hoặc ưu tiên từng thuộc tính, đó là **quy tắc riêng mà thư viện phải cài đặt** bằng cách duyệt superclass và xử lý metadata. @Inherited một mình không cung cấp chức năng gộp theo từng trường.

## 7. Trường hợp method và field: phân biệt kế thừa thành viên với tra cứu annotation

Cho ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Inherited
@interface Tracked {
}

class SuperController {
    @Tracked
    public void handle() {
    }
}

class ChildController extends SuperController {
}
~~~

Vì ChildController không override **handle**, reflection **ChildController.class.getMethod("handle")** tìm được phương thức public khai báo ở SuperController. Nếu kiểm tra **getDeclaringClass()**, kết quả là **SuperController.class**; khi gọi **getAnnotation(Tracked.class)** trên Method đó, Tracked của SuperController hiển thị.

Bây giờ nếu ChildController override handle mà không gắn lại **@Tracked**:

~~~java
class ChildController extends SuperController {
    @Override
    public void handle() {
    }
}
~~~

Reflection trên **ChildController.class.getDeclaredMethod("handle")** cho một **Method của ChildController** và không tự có Tracked. Sự khác biệt này xuất phát từ việc bạn đang lấy Method nào, không phải vì @Inherited đã từng hoạt động trên method.

Tương tự, field kế thừa và field bị khai báo che khuất là chuyện quản lý thành viên của Java; **@Inherited không tự gắn annotation từ field cha lên field con**. Nếu một framework có cơ chế tìm annotation trên method override hoặc field theo quy tắc riêng, kết quả có thể khác API reflection chuẩn. Khi phân tích hành vi framework, cần đọc tài liệu của chính framework đó.

## 8. Giới hạn với interface và quan hệ nhiều cấp

Giả sử:

~~~java
@Mode("contract")
interface ServiceContract {
}

interface ExtendedContract extends ServiceContract {
}

class ServiceImpl implements ExtendedContract {
}
~~~

Cả **ExtendedContract.class.getAnnotation(Mode.class)** và **ServiceImpl.class.getAnnotation(Mode.class)** đều không tự nhận Mode từ ServiceContract qua @Inherited. Trong khi đó **ServiceContract.class.getAnnotation(Mode.class)** tìm được annotation khai báo trực tiếp.

Lý do là @Inherited chỉ quy định **truy vấn superclass của class declaration**. Nó không quy định đi theo **extends giữa các interface**, cũng không duyệt **implements**.

Nếu một framework muốn hỗ trợ metadata từ interface, nó phải có cơ chế tra cứu bổ sung (ví dụ duyệt **getInterfaces()**, đệ quy interface cha, rồi áp dụng một thứ tự ưu tiên rõ ràng). Quy tắc như vậy là **chính sách của framework**, không nên được coi là kết quả mặc định từ **Class.getAnnotation(...)**.

## 9. Khi nào nên và không nên thiết kế @Inherited?

**Phù hợp** khi annotation mô tả một chính sách ở mức **class** mà bạn muốn các subclass chưa khai báo riêng có thể nhận mặc định theo superclass, chẳng hạn một marker phân loại class hay metadata cấu hình chung cho hệ thống.

Ví dụ, thư viện kiểm tra một annotation phân loại:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ModuleGroup {
    String value();
}

@ModuleGroup("reporting")
class BaseReport {
}

class DailyReport extends BaseReport {
}
~~~

Truy vấn **DailyReport.class.getAnnotation(ModuleGroup.class)** có thể nhận "reporting". Tuy nhiên, hành vi phân nhóm trong sản phẩm chỉ xảy ra nếu thư viện **đọc và sử dụng** thông tin này.

**Không nên dựa vào @Inherited như cơ chế mặc định** khi bạn cần:

- Tra cứu annotation trên các interface, generic type use, method, field, parameter hoặc constructor.
- Gộp từng phần tử cấu hình từ nhiều lớp cha/con theo cách tùy biến.
- Bảo đảm mọi framework cùng hiểu hoặc cùng quét annotation giống Java reflection.
- Áp dụng chính sách bảo mật hoặc logic nghiệp vụ chỉ bằng việc xuất hiện annotation, mà chưa có mã kiểm tra và thực thi tương ứng.

Với những yêu cầu này, cần thiết kế và tài liệu hóa quy tắc đọc metadata cụ thể. Ví dụ framework có thể chủ động duyệt superclass/interface/method và kết hợp annotation bằng logic riêng. Sự có mặt của @Inherited trên annotation type không đồng nghĩa framework chắc chắn sẽ dùng đúng chiến lược đó.

### @Inherited và @Documented

**@Documented** yêu cầu công cụ tạo tài liệu như javadoc đưa annotation vào tài liệu của phần tử được chú thích theo quy tắc công cụ. **@Inherited** tác động đến sự hiện diện của annotation trên class khi tra cứu. Hai meta-annotation giải quyết những vấn đề khác nhau; một kiểu annotation có thể dùng cả hai nếu cần.

## 10. Lỗi thường gặp

| Nhận định hoặc cách làm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gắn @Inherited trực tiếp lên class | @Inherited là meta-annotation cho **annotation type**, không phải class thường | Gắn @Inherited trên khai báo **@interface** |
| Tưởng mọi annotation đều tự được class con kế thừa | Cần @Inherited trên chính kiểu annotation | Xác minh định nghĩa annotation |
| Dùng getDeclaredAnnotation để tìm annotation từ superclass | API **Declared** bỏ qua kế thừa | Dùng **getAnnotation** khi muốn tính inherited |
| Mong annotation từ interface truyền sang implements | @Inherited không duyệt interface | Tự duyệt interface hoặc dùng công cụ có quy tắc rõ ràng |
| Mong method override tự nhận annotation method cha | @Inherited không có tác dụng với method | Đọc method cha hoặc xử lý kế thừa metadata bằng logic riêng |
| Bỏ @Retention(RUNTIME) rồi truy vấn bằng reflection | Mặc định CLASS không đủ cho reflection runtime | Dùng RUNTIME nếu cần đọc lúc chạy |
| Mong subclass chỉ ghi đè một element của annotation cha | Annotation trực tiếp của subclass thay thế hiệu lực của annotation cha cùng kiểu | Khai báo đủ giá trị hoặc thiết kế cơ chế merge riêng |
| Nghĩ annotation đã được chép vào bytecode của subclass | @Inherited quy định tra cứu | So sánh **getAnnotation** với **getDeclaredAnnotation** và kiểm tra class file |
| Suy ra @Inherited tự áp dụng quyền truy cập hoặc validation | Annotation chỉ chứa metadata | Thành phần sử dụng phải đọc và thi hành chính sách |

## 11. Bài tập tự kiểm tra

**Bài 1.** Cho:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}

@Region("north")
class A {
}

class B extends A {
}

@Region("south")
class C extends B {
}

class D extends C {
}
~~~

Khi gọi **getAnnotation(Region.class).value()** trên từng class, kết quả tương ứng là: **A = north**, **B = north**, **C = south**, **D = south**. B nhận từ A, còn D nhận từ C vì C là lớp gần hơn có khai báo trực tiếp Region.

**Bài 2.** Với B và D ở trên, **getDeclaredAnnotation(Region.class)** trả về gì? **null** ở cả hai vì B và D không tự khai báo Region.

**Bài 3.** Nếu **interface I** có **@Region("shared")** và **class E implements I**, **E.class.getAnnotation(Region.class)** có trả về Region không? **Không**, vì @Inherited không đi qua implements.

**Bài 4.** Nếu class cha có annotation trên method **run()**, class con override **run()** không gắn annotation, @Inherited có làm method con nhận annotation không? **Không**. Chỉ khi framework tự viết quy tắc tìm trong các method cha thì mới có thể xem metadata method cha là nguồn hỗ trợ.

**Bài 5.** Class F tự khai báo **@Region("east")** và extends A. Điều gì được ưu tiên? **Annotation trực tiếp @Region("east")** trên F. Java không gộp giá trị "east" với "north".

## 12. Tài liệu tham khảo chính thức

- **Java SE 17 — java.lang.annotation.Inherited:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html — quy định rõ tra cứu superclass, không áp dụng cho interface hoặc các vị trí không phải class.
- **Java Language Specification §9.6.4.3 — @Inherited:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3 — mô tả annotation inherited trên class.
- **Java SE 17 — Class.getAnnotation/getDeclaredAnnotation:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — phân biệt annotation hiện diện và annotation trực tiếp.
- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — thuật ngữ directly present, present, associated và phương thức tra cứu annotation.

Khi gặp câu hỏi “annotation của lớp cha có áp dụng cho lớp con không?”, cần xác định trước **kiểu annotation có @Inherited không**, **annotation được gắn lên class hay thành viên**, **quan hệ là extends hay implements**, và **API nào đang được gọi**. Bốn điều này quyết định kết quả đọc metadata trong Java reflection.
