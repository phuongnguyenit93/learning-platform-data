# Phạm vi lưu giữ và khả năng đọc siêu dữ liệu trong AOP

> **Mục tiêu:** Hiểu vòng đời của metadata, nhất là Java annotations, từ mã nguồn qua quá trình biên dịch, class file, class loading đến runtime; phân biệt **phạm vi lưu giữ (retention)** với **vị trí áp dụng (target)** và **khả năng truy cập (visibility/reading mechanism)**; biết vì sao một annotation có thể tồn tại trong class file nhưng không được Java Reflection trả về; hiểu tác động tới annotation-based pointcut, advice, weaving, proxy, inheritance, repeatable annotations, type-use, generic signatures, parameter names và class loader. Bài trình bày kiến thức Aspect-Oriented Programming (AOP) cơ bản và nâng cao nói chung, không giả định một bộ dệt hay framework chuyên biệt. Có hai chương trình Java 17 độc lập để thực hành.

## 1. Bài toán thực tế: có annotation nhưng advice không đọc được

Giả sử lập trình viên đánh dấu một method:

~~~java
@MarkedForAudit
public void transfer() {
    // logic nghiệp vụ
}
~~~

Một bộ chọn điểm can thiệp dựa trên annotation có thể cần biết method này có MarkedForAudit hay không. Tuy nhiên, chỉ nhìn thấy annotation ở source code **chưa đủ** để kết luận nó sẽ được tìm thấy qua Reflection lúc chạy.

Hãy đặt ba câu hỏi riêng:

1. **Annotation được phép đặt ở đâu?** Trên type, method, field, parameter, constructor, type-use hay một vị trí khác?
2. **Annotation được giữ đến giai đoạn nào?** Chỉ source, class file hoặc runtime?
3. **Ai đọc annotation, bằng cơ chế gì và tại thời điểm nào?** Compiler/annotation processor, class-file parser/weaver, Java Reflection, hay một index được tạo sẵn?

Cùng một annotation có thể phù hợp với một cơ chế biên dịch nhưng không phù hợp với một advice chỉ sử dụng Reflection runtime. Đây là nguồn gốc của nhiều vấn đề “pointcut không khớp” hoặc “metadata biến mất”.

## 2. Metadata là gì trong bối cảnh AOP?

**Metadata** là dữ liệu mô tả chương trình hoặc hoạt động thực thi, thay vì bản thân kết quả nghiệp vụ. Các nhóm thường gặp:

- **Type metadata:** class/interface, generic signature, modifiers, superclass và interfaces.
- **Member metadata:** methods, constructors, fields, tên, tham số, kiểu trả về, throws declaration.
- **Annotation metadata:** annotation type, element values, defaults, retention, targets, repeatable/inherited rules.
- **Source-related metadata:** debug line numbers, source filename và một số thông tin do compiler giữ lại.
- **Runtime join point context:** target object, current arguments, return value, exception, call-site identity hoặc control-flow context nếu cơ chế hỗ trợ.

Không nên đồng nhất **metadata tĩnh về mã chương trình** với **ngữ cảnh động của một lần thực thi**. Annotation @Audit trên method là mô tả có thể dùng lại giữa nhiều lời gọi; requestId của một lần gọi là dữ liệu runtime thuộc một execution/request scope.

Một aspect có thể kết hợp cả hai: dùng metadata tĩnh để quyết định có can thiệp hay không, rồi dùng context động khi advice thực sự chạy.

## 3. Vòng đời tổng quát của metadata

~~~text
Java source
   |
   | parser / compiler / annotation processing
   v
Compiled class files
   |
   | binary analysis / weaving / transformation
   v
Class loading + linking
   |
   | Java Reflection or runtime metadata APIs
   v
Runtime interception / advice
~~~

Mỗi tầng có tập dữ liệu riêng. **Không phải mọi thông tin từ source đều được giữ trong bytecode**, và không phải mọi dữ liệu có trong bytecode đều được Reflection cung cấp.

Một bộ dệt ở compile time có thể có thông tin source hoặc compiler model. Một class-file weaver có thể đọc attributes từ binary. Một interceptor chạy sau khi class đã được nạp thường dựa trên những thông tin mà runtime hoặc index riêng cung cấp.

Do đó khi một annotation-based aspect không chọn đúng method, câu đầu tiên nên là **“cơ chế nào đang đọc metadata ở giai đoạn nào?”**, thay vì cho rằng annotation chưa được viết đúng.

## 4. Ba mức RetentionPolicy trong Java

Java có ba chính sách lưu giữ annotation do java.lang.annotation.RetentionPolicy định nghĩa:

| RetentionPolicy | Ý nghĩa chính | Reflection runtime thông thường đọc được? |
|---|---|---|
| **SOURCE** | Annotation được compiler loại bỏ, không tồn tại như runtime annotation của class file | Không |
| **CLASS** | Annotation được ghi vào class file, nhưng không bắt buộc JVM giữ để Java Reflection truy cập | Không qua Reflection thông thường |
| **RUNTIME** | Annotation được giữ trong class file và JVM cung cấp để truy vấn qua Reflection phù hợp | Có, nếu truy vấn đúng phần tử và semantics |

Lưu ý kỹ thuật: retention không phải “cấp độ ưu tiên” của pointcut. Nó quyết định **annotation tồn tại tới đâu**; cơ chế AOP vẫn phải chọn đúng nơi tìm và đúng loại join point.

### 4.1. RetentionPolicy.SOURCE

Annotation SOURCE hữu ích cho compile-time checking, code generation, thông báo từ annotation processor hoặc một số công cụ phân tích source.

Sau khi compiler loại bỏ annotation này khỏi class file thông thường, một runtime advice sử dụng Method.getAnnotation sẽ không tìm thấy nó.

Không có nghĩa SOURCE annotation là “vô dụng với AOP”: một compiler-time transformation/analysis có quyền truy cập source hoặc compiler representation phù hợp vẫn có thể xử lý nó. Nhưng sau đó muốn can thiệp runtime, phải dựa vào **kết quả đã được sinh/biến đổi**, chứ không kỳ vọng Reflection thấy SOURCE annotation.

### 4.2. RetentionPolicy.CLASS

Annotation CLASS được ghi trong class file, thường nằm trong các annotation attributes không hiển thị với Reflection runtime.

Một class-file reader hoặc weaver có khả năng đọc binary metadata có thể dùng annotation CLASS để quyết định transformation trước khi thực thi. Nhưng Java Reflection như getAnnotation hoặc isAnnotationPresent không trả annotation này theo cách thông thường.

Đây là khác biệt quan trọng: **có trong .class không đồng nghĩa có trong kết quả Reflection**.

### 4.3. RetentionPolicy.RUNTIME

Annotation RUNTIME được ghi trong class file và có thể được cung cấp qua các API Reflection tương ứng, ví dụ:

- Class.getAnnotation.
- Method.getDeclaredAnnotation.
- Field.getAnnotations.
- Constructor.getAnnotation.
- Parameter.getAnnotation.
- AnnotatedType.getAnnotation khi metadata được gắn trên type-use tương ứng.

Tuy nhiên, không phải cứ RUNTIME là mọi phương thức trên mọi object đều trả ra annotation. Còn phải chọn **đúng AnnotatedElement, đúng reflection object, đúng luật inheritance/repeatability, đúng class loader**.

## 5. Không khai báo @Retention mặc định ra sao?

Nếu một annotation type **không khai báo @Retention**, Java áp dụng retention mặc định **CLASS**.

Ví dụ minh họa:

~~~java
@interface InternalMarker {}
~~~

Nó không tương đương với RUNTIME. Nếu một thư viện AOP chỉ có runtime reflection, việc quên @Retention(RetentionPolicy.RUNTIME) là một nguyên nhân rất thường gặp khiến pointcut annotation không nhận diện được dấu đánh dấu.

Nên quy định rõ retention ngay khi thiết kế annotation dành cho runtime advice, thay vì phụ thuộc mặc định không phù hợp.

## 6. @Retention tự nó cũng là metadata

Một annotation type được khai báo như:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Audited {}
~~~

Bản thân @Retention là một **meta-annotation**, tức annotation gắn trên khai báo của annotation type khác.

Có thể truy vấn mô tả của annotation type nếu meta-annotation ấy hiện diện phù hợp. Nhưng điều đó không thay thế kiểm tra annotation trên **method cụ thể**.

Cần phân biệt:

- Audited.class: annotation type.
- Audited.class.getAnnotation(Retention.class): retention metadata của annotation type.
- Method.getAnnotation(Audited.class): annotation instance khai báo trên method, nếu có và nếu runtime đọc được.

Hai thao tác khác nhau trả lời hai câu hỏi khác nhau.

## 7. @Target không phải @Retention

**@Target** xác định annotation type được dùng ở những vị trí nào theo các ElementType cho phép. Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface BoundaryMarker {}
~~~

**@Retention** xác định mức lưu giữ; **@Target** xác định vị trí hợp lệ. Một annotation có @Target(METHOD) và @Retention(SOURCE) vẫn không được runtime Reflection thấy.

Ngược lại, @Retention(RUNTIME) và @Target(PARAMETER) không có nghĩa Class.getAnnotation sẽ thấy nó: annotation được gắn trên **parameter declaration**, phải truy vấn Parameter tương ứng.

### 7.1. Một số ElementType hay gặp

| ElementType | Vị trí | Cách đọc runtime điển hình khi retention RUNTIME |
|---|---|---|
| TYPE | Class, interface, enum hoặc annotation type declaration phù hợp | Class |
| METHOD | Method declaration | Method |
| CONSTRUCTOR | Constructor declaration | Constructor |
| FIELD | Field declaration | Field |
| PARAMETER | Formal parameter declaration | Parameter |
| ANNOTATION_TYPE | Khai báo annotation type | Class của annotation type |
| TYPE_PARAMETER | Khai báo type parameter | TypeVariable với annotation APIs |
| TYPE_USE | Vị trí sử dụng kiểu, ví dụ return type, generic argument | AnnotatedType và các biến thể |

Không nên lấy cùng một annotation chỉ vì nó được đặt “gần” method trong source. **Vị trí cú pháp và API Reflection tương ứng rất quan trọng.**

## 8. TYPE_USE có nghĩa khác METHOD

Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNullType {}

class Example {
    public @NonNullType String display() {
        return "ok";
    }
}
~~~

Đây chỉ là đoạn minh họa, không phải một file Java độc lập.

NonNullType được gắn trên **return type use**, không nhất thiết là annotation của method declaration. Đọc qua Method.getAnnotations có thể không thấy; hãy xét Method.getAnnotatedReturnType rồi đọc annotation trên AnnotatedType.

Nếu một annotation được khai báo cho cả METHOD và TYPE_USE, cần xem cách đặt trong source và các API đọc phù hợp. Không thể suy method-level pointcut match từ mọi type-use annotation nằm gần chữ ký.

## 9. Ví dụ Java 17 số 1 — SOURCE, CLASS, RUNTIME và @Inherited

Chương trình này dùng ba annotation với retention khác nhau trên cùng class và method. Nó còn dùng một @Inherited annotation trên class cha để chứng minh:

1. Reflection chỉ đọc được RuntimeTag trong ba loại retention trên một class/method.
2. @Inherited có tác dụng ở **class-level annotation inheritance** theo quy tắc Java.
3. Override method trong subclass **không tự thừa hưởng annotation declaration của method cha**.

Đây là Java Reflection thuần để quan sát metadata. Nó không mô phỏng một engine AOP hoàn chỉnh.

Lưu file **RetentionVisibilityDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class RetentionVisibilityDemo {
    @Retention(RetentionPolicy.SOURCE)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface SourceTag {}

    @Retention(RetentionPolicy.CLASS)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface ClassTag {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @interface RuntimeTag {
        String value();
    }

    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface InheritedPolicy {
        String value();
    }

    @SourceTag
    @ClassTag
    @RuntimeTag("sample")
    static class Sample {
        @SourceTag
        @ClassTag
        @RuntimeTag("work")
        public void work() {}
    }

    @InheritedPolicy("from-parent")
    static class Parent {
        @RuntimeTag("parent-method")
        public void action() {}
    }

    static class Child extends Parent {
        @Override
        public void action() {}
    }

    public static void main(String[] args) throws Exception {
        Class<Sample> type = Sample.class;
        Method work = type.getDeclaredMethod("work");

        System.out.println("[type] source="
                + type.isAnnotationPresent(SourceTag.class));
        System.out.println("[type] class="
                + type.isAnnotationPresent(ClassTag.class));
        System.out.println("[type] runtime="
                + type.getAnnotation(RuntimeTag.class).value());

        System.out.println("[method] source="
                + work.isAnnotationPresent(SourceTag.class));
        System.out.println("[method] class="
                + work.isAnnotationPresent(ClassTag.class));
        System.out.println("[method] runtime="
                + work.getAnnotation(RuntimeTag.class).value());

        System.out.println("[child] inherited="
                + Child.class.getAnnotation(
                        InheritedPolicy.class).value());
        System.out.println("[child] declared="
                + (Child.class.getDeclaredAnnotation(
                        InheritedPolicy.class) != null));

        Method overridden =
                Child.class.getDeclaredMethod("action");
        System.out.println("[override] runtime="
                + overridden.isAnnotationPresent(RuntimeTag.class));

        Method parentMethod =
                Parent.class.getDeclaredMethod("action");
        System.out.println("[parent-method] runtime="
                + parentMethod.getAnnotation(
                        RuntimeTag.class).value());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RetentionVisibilityDemo.java
java RetentionVisibilityDemo
~~~

**Stdout xác định:**

~~~text
[type] source=false
[type] class=false
[type] runtime=sample
[method] source=false
[method] class=false
[method] runtime=work
[child] inherited=from-parent
[child] declared=false
[override] runtime=false
[parent-method] runtime=parent-method
~~~

### 9.1. Vì sao SOURCE và CLASS đều trả false?

isAnnotationPresent dùng Reflection runtime đối với loại annotation cần truy vấn. SOURCE không được giữ trong class file; CLASS có thể còn trong class file nhưng không phải runtime-visible annotation qua API này.

Cả hai trả false ở đây **không có nghĩa** compiler hoặc binary transformer không thể đọc ClassTag khi dùng đúng công cụ và giai đoạn tương ứng.

### 9.2. Vì sao RuntimeTag đọc được?

RuntimeTag có retention RUNTIME, được gắn đúng class/method và truy vấn trên đúng AnnotatedElement. getAnnotation trả annotation instance, nên có thể lấy element value.

Kết quả phản ánh **vị trí khai báo thực tế**, không phải một pointcut match tự động.

### 9.3. @Inherited không phải copy annotation xuống subclass

Child không khai báo trực tiếp InheritedPolicy, nhưng Class.getAnnotation có thể thấy annotation theo semantics @Inherited đối với annotation type ở class hierarchy.

getDeclaredAnnotation chỉ xét **khai báo trực tiếp** trên Child, nên trả null và biến declared là false.

Không được suy rằng class file của Child thực sự có một bản annotation được copy vào phần khai báo. Đây là quy tắc truy vấn được runtime hỗ trợ.

### 9.4. Override method không tự kế thừa method annotation

Child.action override Parent.action nhưng không khai báo RuntimeTag. Reflection trên **Child declared Method** không thấy RuntimeTag.

Parent.action vẫn có annotation của chính nó. Nếu một pointcut hoặc adapter muốn coi annotation trên method gốc như áp dụng cho override, nó phải **định nghĩa và thực hiện resolution strategy** tương ứng. @Inherited không tự cung cấp ngữ nghĩa đó cho method.

### 9.5. Vì sao ví dụ không chứng minh runtime weaving?

Reflection cho thấy metadata đọc được bằng JDK. Một engine AOP còn cần **khả năng chặn join point thích hợp** và quyết định quy tắc matching riêng. RUNTIME retention là điều kiện thuận lợi cho reflection-based matching nhưng không tự làm một method trở thành join point có thể advice trong mọi engine.

## 10. CLASS retention trong class file có thể trông thế nào?

Một Java class file có các attributes dùng để biểu diễn annotation. Trong thực hành, công cụ phân tích binary như javap -v có thể giúp quan sát những nhóm metadata:

- **RuntimeVisibleAnnotations:** dùng để chứa những annotation declaration có runtime visibility.
- **RuntimeInvisibleAnnotations:** dùng cho một số annotation declaration giữ trong class file nhưng không runtime-visible.
- Các biến thể attributes tương ứng cho parameter annotations và type annotations.

Tên attributes ở mức JVM class-file format; không đồng nghĩa Reflection có một API chung để đọc mọi RuntimeInvisibleAnnotations.

### 10.1. Cách tự khảo sát binary

Sau khi biên dịch ví dụ 1, có thể dùng công cụ từ JDK như:

~~~bash
javap -v RetentionVisibilityDemo
~~~

Để khảo sát nested class cần truyền tên binary class hoặc tệp .class thích hợp, ví dụ trên một shell hỗ trợ quote:

~~~bash
javap -v 'RetentionVisibilityDemo$Sample.class'
~~~

Đây là thao tác khảo sát, không cung cấp một stdout cố định vì output của javap -v dài và có thể khác theo compiler/JDK build.

Điều cần quan sát là RuntimeTag có metadata runtime-visible, ClassTag có thể xuất hiện như runtime-invisible trong class file, còn SourceTag không có annotation declaration entry tương ứng trong class file.

## 11. Annotation processor đọc metadata ở giai đoạn nào?

Java annotation processing hoạt động trong bối cảnh compilation, dùng mô hình elements/types do compiler cung cấp qua các API xử lý annotation tương ứng.

Một processor có thể nhận thông tin về annotations ở source/compilation model, kể cả annotation có retention SOURCE, nếu annotation đó hiện diện ở giai đoạn xử lý phù hợp.

Nhưng processor không tự làm runtime Reflection thấy SOURCE annotation. Nếu cần hành vi runtime, một processor có thể **sinh mã, metadata index hoặc các cấu trúc hỗ trợ** để runtime sử dụng, trong phạm vi build pipeline được thiết kế.

### 11.1. Không nhầm annotation processor với runtime advice

Annotation processor không có nghĩa mỗi lần một method được gọi thì processor lại chạy. Nó thường chạy trong quá trình compile, còn advice là hành vi tại những runtime join points (hoặc code đã được transform).

Đây là hai tầng khác nhau:

~~~text
Compile-time:
  annotation discovery -> validation / code generation

Runtime:
  selected join point -> advice executes
~~~

Nếu build không chạy processor, output sinh mã/index có thể thiếu, dù annotation type vẫn có retention đúng. Cần kiểm tra cả **build configuration**.

## 12. Class-file weaving có thể dùng dữ liệu mà Reflection không thấy

Một binary weaver đọc bytecode trước runtime có thể dựa trên annotation với retention CLASS, vì annotation này được compiler ghi vào class file.

Tuy nhiên, có các điều kiện:

1. Class thực sự nằm trong phạm vi được weaver quét.
2. Công cụ hỗ trợ đọc annotation attribute tương ứng.
3. Binary còn annotation đó sau compiler/optimizer/transformer trước đó.
4. Annotation được gắn đúng element.
5. Matching rule của weaver thực sự cho phép selection theo metadata ấy.
6. Weaving được áp dụng trước khi class cần sử dụng theo mô hình tương ứng.

Do đó không nên khẳng định tất cả các engine chỉ làm runtime reflection. Cũng không nên khẳng định **mọi engine đọc được CLASS annotations**. Cơ chế là yếu tố quyết định.

## 13. RUNTIME retention không bảo đảm mọi annotation đều được nhìn thấy

Các nguyên nhân phổ biến khiến getAnnotation trả null dù annotation type có RUNTIME:

- Truy vấn nhầm Class thay vì Method.
- Truy vấn nhầm Method declaration thay vì return AnnotatedType.
- Truy vấn interface method trong khi annotation nằm trên implementation method, hoặc ngược lại.
- Phương thức con override nhưng không mang annotation khai báo của phương thức cha.
- Dùng getDeclaredAnnotation trong khi muốn xem @Inherited class-level annotation.
- Repeatable annotations được compiler đóng vào container.
- Annotation chỉ gắn trên bridge/synthetic method khác.
- Class object đến từ class loader không phù hợp.
- Tên annotation giống nhau nhưng class identity khác nhau.
- Công cụ AOP không hỗ trợ join point dù reflection đọc được metadata.

**Cần chẩn đoán đồng thời retention, vị trí, API đọc và cơ chế can thiệp.**

## 14. @Inherited có phạm vi hẹp

@Inherited là meta-annotation có tác động tới việc tra cứu một annotation type trên **class hierarchy** theo quy tắc của Class annotation API.

Nó không đồng nghĩa:

- Annotation method override tự được kế thừa.
- Annotation field của superclass tự trở thành declared annotation trên field subclass.
- Annotation từ interface được Class.getAnnotation kế thừa theo mọi trường hợp.
- Annotation type-use được tự chuyển từ một vị trí type-use cha sang con.
- Annotation được copy vào bytecode của subclass.

Nếu một annotation-based pointcut muốn nhận diện interface metadata khi target implementation không khai báo annotation trực tiếp, cần một **quy tắc lookup riêng** (hoặc tính năng công cụ được đặc tả), không dựa mù quáng vào @Inherited.

## 15. Annotation trên interface so với implementation

Xét mô hình:

~~~text
interface Repository:
   @Audited
   find()

class SqlRepository implements Repository:
   find()   // không ghi annotation ở đây
~~~

Reflection trên Method object của Repository.find có thể thấy annotation; Reflection trên method declaration SqlRepository.find không tự thấy cùng annotation.

Một interceptor có thể nhận Method mô tả interface hoặc implementation tùy cơ chế proxy/call path. Nếu adapter đọc annotation trực tiếp từ Method mà runtime cung cấp mà không cân nhắc nguồn Method, behavior có thể thay đổi khi đổi cơ chế can thiệp.

### 15.1. Thiết kế một lookup strategy rõ ràng

Các lựa chọn khái niệm:

1. **Exact declaration only:** chỉ annotation trên Method đang xét.
2. **Implementation-first:** ưu tiên concrete implementation rồi xét interface.
3. **Interface-first:** lấy hợp đồng interface trước, implementation có quy tắc override riêng.
4. **Hierarchy walk:** duyệt superclasses/interfaces theo thuật toán được định nghĩa.
5. **Explicit conflict:** báo lỗi khi hai nguồn đưa giá trị mâu thuẫn.

Không có một chiến lược duy nhất đúng trong mọi domain. Nhưng phải **tài liệu hóa precedence**, tránh “annotation thay đổi theo proxy type” ngoài ý muốn.

## 16. getAnnotation và getDeclaredAnnotation khác nhau

Trên Class:

- getDeclaredAnnotation chọn annotation **khai báo trực tiếp** trên class đó.
- getAnnotation có thể xét ngữ nghĩa kế thừa cho annotation type đánh dấu @Inherited.

Trên Method, Field hoặc Parameter, không được suy có cùng cơ chế kế thừa kiểu class. Annotation declared của method con và method cha là những khai báo khác nhau.

Ngoài ra có API **getAnnotationsByType** và **getDeclaredAnnotationsByType**, quan trọng với annotation lặp. Nếu dùng API trả một annotation đơn trong khi annotation có thể lặp, kết quả có thể không phản ánh đủ dữ liệu.

## 17. Repeatable annotations có container

Java hỗ trợ khai báo annotation có thể lặp bằng @Repeatable. Khi có nhiều annotation cùng loại trên một declaration, compiler có thể biểu diễn chúng thông qua một **container annotation**.

Ví dụ khái niệm:

~~~text
@Rule("audit")
@Rule("trace")
void execute()
~~~

Một lời gọi getAnnotation(Rule.class) không phải API phù hợp để truy vấn **toàn bộ** các Rule khi chúng được đóng vào container.

Nên dùng getAnnotationsByType(Rule.class) hoặc getDeclaredAnnotationsByType theo nhu cầu inheritance/declaration. Khi đọc binary, cần hiểu cách container được biên dịch và retention/target constraints tương ứng.

## 18. Ví dụ Java 17 số 2 — repeatable, parameter và type-use

Chương trình này chứng minh:

1. Hai @Rule được đọc bằng getAnnotationsByType.
2. Container @Rules có thể được thấy ở Method.
3. Parameter annotation có API riêng.
4. Type-use annotation trên return type được đọc bằng getAnnotatedReturnType.
5. Parameter name metadata chỉ ổn định khi biên dịch với cờ -parameters trong bài này.

Lưu file **MetadataTraversalDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.stream.Collectors;

public class MetadataTraversalDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @Repeatable(Rules.class)
    @interface Rule {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Rules {
        Rule[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Argument {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface NonEmpty {}

    static class Api {
        @Rule("audit")
        @Rule("trace")
        public @NonEmpty String convert(
                @Argument("input") String input) {
            return input;
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = Api.class.getDeclaredMethod(
                "convert", String.class);

        Rule[] rules = method.getAnnotationsByType(Rule.class);
        String joined = Arrays.stream(rules)
                .map(Rule::value)
                .collect(Collectors.joining(","));

        System.out.println("[method] rule-count="
                + rules.length);
        System.out.println("[method] rules=" + joined);
        System.out.println("[method] has-container="
                + (method.getAnnotation(Rules.class) != null));
        System.out.println("[method] direct-rule="
                + (method.getAnnotation(Rule.class) != null));

        Parameter parameter = method.getParameters()[0];
        System.out.println("[param] annotation="
                + parameter.getAnnotation(Argument.class).value());
        System.out.println("[param] name=" + parameter.getName());
        System.out.println("[param] name-present="
                + parameter.isNamePresent());

        boolean returnMarked =
                method.getAnnotatedReturnType()
                        .isAnnotationPresent(NonEmpty.class);
        System.out.println("[return-type] non-empty="
                + returnMarked);
        System.out.println("[method] has-type-use-as-declaration="
                + method.isAnnotationPresent(NonEmpty.class));
    }
}
~~~

Biên dịch và chạy **đúng cờ -parameters**:

~~~bash
javac -parameters MetadataTraversalDemo.java
java MetadataTraversalDemo
~~~

**Stdout xác định khi dùng JDK 17 và lệnh trên:**

~~~text
[method] rule-count=2
[method] rules=audit,trace
[method] has-container=true
[method] direct-rule=false
[param] annotation=input
[param] name=input
[param] name-present=true
[return-type] non-empty=true
[method] has-type-use-as-declaration=false
~~~

### 18.1. Tại sao getAnnotation(Rule.class) là false?

Hai Rule khai báo trên method được biểu diễn dưới một container Rules theo luật repeatable annotation. getAnnotation(Rule.class) không phải phép “mở mọi container và trả một trong hai Rule”.

getAnnotationsByType xử lý những annotations trực tiếp/gián tiếp hiện diện theo semantics Java. Kết quả gồm hai Rule, theo thứ tự được bảo toàn phù hợp.

### 18.2. Tại sao container tồn tại?

@Repeatable(Rules.class) trỏ tới container annotation type. Trong trường hợp có hai Rule, Method có annotation container Rules chứa hai phần tử.

Nếu một AOP adapter chỉ đọc getDeclaredAnnotations và không unwrap repeatable container, có thể không nhận diện từng Rule riêng. Chọn API đọc phù hợp là trách nhiệm metadata lookup.

### 18.3. Vì sao annotation parameter không nằm trên Method trực tiếp?

@Argument được gắn với formal parameter. Để lấy nó, ví dụ dùng getParameters()[0] rồi getAnnotation(Argument.class).

Không nên dùng annotation method lookup để suy một parameter đã được đánh dấu. Một annotation-based pointcut dành cho parameter cần biết mapping parameter-index và những loại parameter mà mô hình hỗ trợ.

### 18.4. Vì sao @NonEmpty không xuất hiện như annotation declaration của method?

NonEmpty có @Target(TYPE_USE). Trong ví dụ nó gắn trên **String return type use**, nên method.getAnnotatedReturnType thấy nó, còn method.isAnnotationPresent không thấy annotation declaration thuộc METHOD.

Đây là khác biệt giữa **metadata về method** và **metadata về type nằm trong chữ ký của method**.

### 18.5. Vì sao phải dùng -parameters?

Java class file có thể giữ method parameter name metadata nhờ tùy chọn biên dịch -parameters. Nếu không có, Reflection có thể cung cấp tên tổng hợp như arg0 và isNamePresent() là false.

Annotation parameter không tự đòi hỏi -parameters để được đọc; đây là hai nhóm metadata khác nhau. Cờ -g để thêm debug information cũng không thay thế trực tiếp hợp đồng -parameters của Parameter.getName().

## 19. Sự khác nhau giữa annotation element và annotation instance

Một annotation type có thể khai báo elements:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface LogRule {
    String category() default "general";
    int level() default 1;
}
~~~

Đây là một đoạn Java minh họa.

**Element values** có thể đến từ giá trị người dùng chỉ định hoặc default trong annotation type. Khi Reflection trả annotation instance, gọi các element methods như category() đọc giá trị hiệu lực theo semantics runtime.

Điều này quan trọng khi xây cache:

- Cache chỉ tên annotation type có thể thiếu element values.
- Cần key theo nơi khai báo cụ thể nếu các method có giá trị khác nhau.
- Một default value thay đổi theo phiên bản annotation type có thể làm kết quả mới khác giá trị cũ.
- Nếu class file và annotation type bị lệch phiên bản, runtime annotation parsing có thể gặp lỗi.

Không tự gán rằng hai method có cùng annotation type sẽ có cùng chính sách xử lý.

## 20. Metadata có thể tồn tại nhưng không còn truy cập được đúng cách

Một annotation retention RUNTIME trong .class có thể vẫn không được công cụ tìm thấy vì:

1. Công cụ chọn nhầm method.
2. Class được nạp từ bản khác.
3. Runtime đang dùng một class loader khác.
4. Một weaver/proxy chỉ quan sát interface method.
5. Annotation được đặt trên generic bridge counterpart.
6. Tên annotation được kiểm tra như String thay vì class identity.
7. Bộ tối ưu/biến đổi binary không giữ metadata như mong đợi.
8. API tìm annotation không hỗ trợ trường hợp repeatable/type-use cần xét.
9. Công cụ chọn sai loại join point.
10. Annotation query bị thực hiện sau khi metadata đã được snapshot theo rules riêng của engine.

Nên tách một phép thử **JDK Reflection thuần** khỏi một phép thử **AOP pointcut selection thực tế** để xác định lỗi ở tầng nào.

## 21. Reflection method object chưa chắc là implementation method

Trong một số cơ chế proxy qua interface, một interceptor có thể nhận Method từ interface. Với class-level weaving hoặc reflection trực tiếp trên target, nó có thể nhận Method trên concrete class.

Nếu @Audit được đặt trên implementation nhưng Method đang được hỏi thuộc interface chưa đánh dấu, isAnnotationPresent có thể là false.

Một lookup strategy có thể phải phân giải method concrete bằng:

- Tên.
- Loại tham số thực hoặc descriptor.
- Declaring type và runtime target type.
- Visibility/override rules.
- Bridge/synthetic method handling.
- Interface hierarchy policy.

Không chỉ tìm theo tên method, bởi **overloads** có thể cùng tên nhưng annotation khác nhau.

## 22. Annotation trên superclass method và override

Trường hợp:

~~~text
Base.process() has @Logged
Child.process() overrides with no annotation
~~~

Java không tự sao chép @Logged xuống Child.process. Một AOP policy có thể muốn kế thừa ngữ nghĩa annotation từ Base, nhưng đó là **quy tắc lựa chọn do hệ thống định nghĩa**.

Cần làm rõ:

- Annotation ở Base có hiệu lực trên override không?
- Annotation ở Child có ghi đè hay cộng thêm?
- Nếu Base/Interface có annotation mâu thuẫn, ai thắng?
- Nếu Child không có override mà kế thừa method, Method reflection nào được truy vấn?
- Nếu class có bridge methods, cần normalize về method logic nào?

Một quy tắc không rõ ràng có thể khiến việc thêm override làm mất audit mà không ai nhận ra.

## 23. Bridge và synthetic methods trong Java generics

Java compiler có thể sinh **bridge methods** để bảo toàn polymorphism sau type erasure. Chúng là methods runtime thực tế ở bytecode và có thể xuất hiện trong Reflection.

Nếu một AOP tool quan sát method execution, một call có thể đi qua bridge rồi tới implementation method tùy bytecode và dispatch. Không nên tự đếm chúng là hai thao tác nghiệp vụ riêng nếu policy chỉ muốn một logical invocation.

Khi tìm annotation:

- Method.isBridge() giúp phân biệt bridge.
- Method.isSynthetic() cho biết method được tạo tổng hợp ở một số trường hợp.
- Generic signature và erased descriptor khác nhau.
- Annotation có thể nằm trên declaration logic hoặc được compiler xử lý theo rules riêng.

Không tự giả định mọi compiler copy tất cả annotations giống nhau sang bridge method, nhất là khi xử lý version khác nhau. Cần dùng lookup strategy và test trên compiled classes thật.

## 24. Annotation TYPE_PARAMETER và TYPE_USE trong generic APIs

Một annotation có thể gắn trên khai báo type variable hoặc chỗ sử dụng kiểu tổng quát, ví dụ:

~~~text
class Container<@BoundTag T> { ... }
List<@NonNullType String> values
~~~

Đây là mô tả khái niệm; annotation definitions và các type bounds phải hợp lệ tương ứng mới biên dịch được.

Reflection dùng các APIs khác nhau: TypeVariable có thể là AnnotatedElement cho TYPE_PARAMETER annotations; AnnotatedParameterizedType và AnnotatedType variants cung cấp thông tin về TYPE_USE annotations trên type arguments.

Một method-level pointcut chỉ đọc Method.getAnnotation có thể bỏ qua những annotations ở **type parameter hoặc nested type-use**. Nhưng không có nghĩa mọi AOP engine cần hỗ trợ chúng làm điều kiện chọn join point; đó là khả năng riêng.

## 25. Parameter annotations và parameter names là hai lớp metadata

Ví dụ một method có hai parameters:

~~~text
update(@Sensitive String token, int retries)
~~~

Annotation @Sensitive có thể được lưu dưới dạng parameter annotation nếu retention phù hợp. Parameter name token và retries có thể **không có** trong Reflection nếu compiler không ghi MethodParameters theo cách cần thiết.

Điều đó có nghĩa:

- Có thể biết **parameter 0** được đánh dấu Sensitive.
- Nhưng chưa chắc đọc được tên token.
- Một advice redact arguments nên ưu tiên **vị trí/annotation metadata được xác nhận**, không dựa toàn bộ vào tên tham số khi tên không có.
- Nếu một index đọc source dùng tên nhưng runtime không có, mapping phải được xây nhất quán.

Trong code bảo mật, không được bỏ redaction chỉ vì Parameter.getName() trả arg0.

## 26. Reflection không tự cung cấp mọi thông tin source

Compiler có thể ghi source filename và line numbers trong debug attributes; một số dữ liệu bị loại khi tối ưu hoặc biên dịch với flags khác.

Reflection tiêu chuẩn không cung cấp trực tiếp đầy đủ tất cả line numbers hoặc nguồn gốc pointcut như một AST. Những công cụ bytecode hoặc runtime diagnostics khác có thể dùng class-file attributes để hiển thị line/file, nhưng thông tin có thể thiếu hoặc không chính xác ở generated code.

Đặc biệt với lambdas, synthetic methods và transformed bytecode, không nên suy “line source = join point identity duy nhất” khi định nghĩa chính sách AOP.

## 27. Class loader và danh tính annotation type

Trong JVM, danh tính runtime của một type phụ thuộc vào **binary name và defining class loader**. Hai annotation classes cùng tên nhưng được nạp bởi hai class loaders khác nhau không nhất thiết là cùng type.

Khi dùng:

~~~java
element.getAnnotation(Audited.class)
~~~

Audited.class là một **Class object cụ thể**. Nếu annotation trong target metadata được resolve qua loader khác và type identity không tương thích, lookup có thể không như người viết mong đợi.

Các bối cảnh phức tạp như plugin containers, isolated modules hoặc dynamic loading cần test đúng class loader topology; không dựa vào tên annotation in ra để kết luận có thể cast/truy vấn.

## 28. Module boundaries và access constraints

Java modules và visibility có thể ảnh hưởng cách code Reflection truy cập khai báo và invoke members. Việc **đọc annotation metadata** và việc **truy cập/call một private method** là hai thao tác khác nhau với constraints riêng.

Một AOP runtime có thể có quyền bytecode instrumentation không giống một thư viện Reflection chạy từ module khác.

Không tự coi @Retention(RUNTIME) là quyền vượt qua mọi giới hạn module accessibility, security policy hoặc class loader. Phạm vi can thiệp phải được xác minh độc lập với metadata visibility.

## 29. Annotations không phải lệnh thực thi

Đặt @Timed trên method không tự đo thời gian. Đặt @Audit không tự sinh audit event. Annotation chỉ là metadata; phải có một thành phần hiểu và thực thi chính sách ấy:

~~~text
Annotation declaration
    |
    +-- compiler/processor recognizes it
    |
    +-- weaver uses it as selection/transform rule
    |
    +-- runtime interceptor queries it
    |
    +-- application code reads it explicitly
~~~

Nếu không có consumer thích hợp, annotation có thể chỉ là tài liệu hoặc dấu đánh dấu.

Một Java Reflection query thành công cũng không chứng minh method được tự động interception; phải có join point selection và advice invocation đúng runtime path.

## 30. Annotation-based pointcut phải định nghĩa “annotation ở đâu?”

Một rule kiểu “chặn các method @Audited” còn mơ hồ nếu không nói:

- Annotation đặt trên method **declaration** hay class?
- Nếu annotation trên interface method thì implementation có được tính không?
- Nếu trên method cha bị override thì có tính không?
- Nếu annotation lặp, có đọc toàn bộ rules không?
- Nếu annotation là meta-annotation trên một annotation khác thì có được xét không?
- Nếu method có bridge hoặc synthetic counterpart, chọn method nào?
- Có xét runtime target type hay chỉ declared type?
- Nếu annotation ở return type-use thì có được match không?

Một annotation-driven pointcut tốt phải có **lookup semantics rõ**, không dựa vào tên @Audited chung chung rồi hi vọng mọi framework diễn giải giống nhau.

## 31. Meta-annotation không tự là annotation trực tiếp

Ví dụ:

~~~text
@AuditStereotype
@interface CriticalAction {}

@CriticalAction
void transfer()
~~~

Nếu AuditStereotype được gắn lên **annotation type CriticalAction**, thì transfer trực tiếp có @CriticalAction, không tự có @AuditStereotype trên method.

Một tool có thể hỗ trợ **meta-annotation search**, bằng cách đọc annotation type của các annotations gắn trực tiếp lên method và tiếp tục kiểm tra metadata của chúng. Nhưng đó là **chức năng traversal riêng**, không phải kết quả mặc định của Method.getAnnotation(AuditStereotype.class).

Cần có giới hạn chiều sâu, xử lý cycles/duplicates và precedence nếu tự xây traversal logic. Một annotation type còn có meta-annotations tiêu chuẩn; không nên mọi metadata cấp hệ thống đều bị coi thành nghiệp vụ.

## 32. Cache metadata: đúng đắn trước hiệu năng

Metadata tĩnh thường được dùng nhiều lần. Một AOP runtime có thể cache kết quả resolution để tránh Reflection lặp lại trên hot path.

Những key có thể cần:

- Method object hoặc method descriptor đầy đủ.
- Declaring type và target runtime type khi semantics phụ thuộc.
- Class loader identity.
- Loại annotation hoặc loại query.
- Chiến lược inheritance/interface resolution.
- Có cần đọc repeatable/type-use hay không.

Nếu cache chỉ theo tên method, hai overloads khác annotations có thể bị trộn. Nếu cache giữ strong references tới Class/Method của plugin đã được unload, cache có thể giữ class loader sống lâu ngoài ý định.

Một design cần cân nhắc weak keys, lifetime scope và cache invalidation theo mô hình class loading thực tế.

### 32.1. Cẩn thận với cache giữa các class loaders

Hai classes có cùng fully-qualified name nhưng loader khác nhau có thể mang annotations khác nhau. Cache key chỉ dùng tên String làm kết quả một môi trường dùng sang môi trường khác là không an toàn.

Trong AOP có load-time transformations hoặc plugin reload, cần xem cấu trúc metadata có thay đổi theo phiên bản class/runtime không.

## 33. Precompiled indexes và generated metadata

Một cách khác Reflection runtime là tạo **metadata index** ở build time:

~~~text
Source / class files
    |
    v
Index generator
    |
    v
Metadata registry
    |
    v
Runtime interceptor lookup
~~~

Ưu điểm tiềm năng:

- Giảm Reflection on hot path.
- Có thể dùng dữ liệu mà build-time tool được phép đọc.
- Dễ kiểm tra static consistency.
- Có thể tạo mapping từ annotation sang rule IDs.

Nhưng phải quản lý:

- Phiên bản index so với class files thực sự chạy.
- Class loader/module mapping.
- Method descriptors cho overload/bridge.
- Dữ liệu đã transform sau build.
- Invalidations khi deploy/reload.
- Security của registry và dữ liệu nhạy cảm.

Không mặc định mọi hệ AOP dùng index hoặc index luôn chính xác. Với compilation khác nhau, index stale có thể tệ hơn Reflection chậm nhưng đúng.

## 34. Chọn retention theo consumer thực tế

| Nhu cầu | Lựa chọn nên xem xét |
|---|---|
| Chỉ compile-time validation | SOURCE có thể đủ |
| Tool binary đọc annotation trong class file trước runtime | CLASS có thể phù hợp |
| Java Reflection runtime cần tìm annotation trên method/type | RUNTIME thường cần |
| Một công cụ code generation xử lý annotation khi compile | SOURCE, CLASS hoặc RUNTIME tùy pipeline |
| Cần runtime match theo annotation đã biến đổi | Xem cả retention lẫn transformation và lookup strategy |
| Annotation chỉ làm marker trong tài liệu source | Không nhất thiết cần RUNTIME |
| Metadata type-use cần được runtime đọc | RUNTIME + TYPE_USE + AnnotatedType API đúng |

Chọn retention **không nên chỉ vì “càng giữ lâu càng tốt”**. RUNTIME metadata có overhead class file/runtime và làm API metadata công khai hơn. Nhưng nếu runtime interceptor thật sự phụ thuộc Reflection thì SOURCE/CLASS sẽ không đáp ứng.

## 35. Chi phí của metadata khi dùng rộng

Các chi phí có thể gồm:

- Kích thước class file khi lưu annotation/attributes.
- Nạp/parse metadata ở runtime.
- Reflection lookup lặp lại trong advice.
- Duyệt hierarchy và interfaces.
- Giải quyết repeatable container.
- Phân tích generic AnnotatedType tree.
- Tạo/copy các annotation values.
- Cache giữ Class/Method/class loader references.
- Thời gian match pointcut động nếu cứ lặp metadata resolution.

Cách tối ưu:

1. Chuẩn hóa method key một lần.
2. Cache những kết quả tĩnh theo class loader/lifetime phù hợp.
3. Tránh Reflection mỗi invocation khi không cần.
4. Chỉ duyệt hierarchy theo rule đã định.
5. Không serialize raw annotations vào mọi log.
6. Đo latency trước/sau trong điều kiện weaving thật.
7. Tránh để cache chứa unbounded entries khi có dynamic class loading.

Không đặt mục tiêu tối ưu trước khi bảo đảm **annotation lookup đúng semantics**.

## 36. An toàn và bảo vệ metadata

Annotation values có thể chứa:

- Endpoint names hoặc internal resource paths.
- Thông tin phân loại dữ liệu.
- ID của policy hoặc tên tenant theo thiết kế không phù hợp.
- Tham số điều khiển logging.
- Class references, enum constants hoặc arrays.

Không nên đặt passwords, raw tokens hoặc secrets vào annotation source và trông chờ retention SOURCE sẽ “giấu” được dữ liệu trong hệ quản lý source. Metadata cần được kiểm soát từ **nguồn tạo, nơi lưu tới nơi hiển thị**.

Nếu adapter ghi toàn bộ annotation values vào log, nó có thể vô tình tiết lộ dữ liệu cấu hình. Shared handler nên nhận chỉ những metadata đã được allowlist/redact theo chính sách.

## 37. Các lỗi thường gặp

**Lỗi 1 — Không khai báo @Retention khi cần Reflection.** Default là CLASS; method.getAnnotation trả null.

**Lỗi 2 — Nhầm @Target với @Retention.** METHOD không có nghĩa RUNTIME.

**Lỗi 3 — Class annotation được hỏi qua Method.** Phải chọn đúng AnnotatedElement.

**Lỗi 4 — Type-use annotation được hỏi qua Method.getAnnotations.** Cần AnnotatedType tương ứng.

**Lỗi 5 — Dùng getAnnotation cho repeatables.** Có thể không đọc đủ các annotations gián tiếp qua container.

**Lỗi 6 — Cho rằng @Inherited áp dụng cho method overrides.** Không có quy tắc tự động như vậy.

**Lỗi 7 — Annotation trên interface method nhưng chỉ hỏi implementation Method.** Cần resolution strategy nếu hợp đồng muốn interface inheritance.

**Lỗi 8 — Chọn sai method khi có overload.** Tên không đủ; cần parameter types/descriptors.

**Lỗi 9 — Không xét bridge/synthetic methods.** Pointcut có thể chọn nhầm invocation hoặc metadata lookup lệch.

**Lỗi 10 — Tin rằng có annotation là engine có join point tương ứng.** Metadata visibility và interception coverage khác nhau.

**Lỗi 11 — Cho rằng CLASS annotation không ai đọc được.** Reflection không trả, nhưng class-file reader có thể đọc.

**Lỗi 12 — Cho rằng SOURCE annotation phải xuất hiện trong .class.** Nó thường bị loại ở compilation.

**Lỗi 13 — Không truyền -parameters nhưng muốn dùng Parameter.getName.** Có thể nhận arg0 thay tên thật.

**Lỗi 14 — Dùng cache chỉ theo tên class.** Không xử lý class loaders/versioning.

**Lỗi 15 — Tạo index ở build time rồi không làm mới.** Stale index không phản ánh binary hiện tại.

**Lỗi 16 — Log toàn bộ metadata.** Có thể lộ thông tin và làm tăng overhead.

**Lỗi 17 — Hiểu @Inherited như copy vào subclass bytecode.** Nó là semantics khi tra cứu class-level annotation.

**Lỗi 18 — Nhầm compiled class metadata với runtime arguments.** Annotation không thay thế data context của một lần gọi.

## 38. Ma trận kiểm thử annotation-based AOP

| Ca thử | Cần xác minh |
|---|---|
| SOURCE annotation trên method | Reflection không thấy; compile-time tool có thể xử lý |
| CLASS annotation trên method | Có thể tồn tại trong binary, Reflection không thấy |
| RUNTIME annotation trên method | Reflection trên đúng Method thấy |
| RUNTIME annotation trên class | Reflection trên đúng Class thấy |
| @Retention không khai báo | Mặc định CLASS |
| @Target không cho phép vị trí | Compiler từ chối sử dụng sai |
| @Inherited trên TYPE | Class subclass lookup theo hợp đồng |
| getDeclaredAnnotation trên subclass | Không tự trả annotation chỉ có ở superclass |
| Override method không gắn annotation | Không được coi mặc định là declared annotated |
| Annotation trên interface method | Lookup strategy đúng |
| Repeatable annotation | getAnnotationsByType trả đúng các phần tử |
| Parameter annotation | Parameter đúng index có metadata |
| Parameter name | -parameters semantics đúng |
| Return TYPE_USE annotation | AnnotatedReturnType đúng |
| Two overloaded methods | Không trộn annotations |
| Bridge/synthetic methods | Resolution không tính sai |
| Proxy method khác implementation | Matching được đặc tả |
| Class loader khác | Không dựa tên String đơn lẻ |
| Runtime cache | Không giữ stale metadata |
| Build-time index | Trùng phiên bản binary |
| Weaving scope | Chỉ các classes/joins được hỗ trợ mới có advice |

### 38.1. Hai tầng test cần tách

**Metadata test:** dùng Reflection hoặc class-file tool để chứng minh annotation lưu ở đâu, API đọc thế nào.

**AOP integration test:** chứng minh engine thực sự chọn join point và chạy advice tại ranh giới dự kiến.

Một test Reflection pass không thay thế integration test; một advice không chạy chưa đủ khẳng định retention sai.

## 39. Quy trình chẩn đoán “annotation không được nhận diện”

1. Ghi chính xác annotation type và retention declaration.
2. Nếu không có @Retention, nhớ default CLASS.
3. Kiểm tra @Target tương thích nơi sử dụng.
4. Xác định annotation gắn lên TYPE/METHOD/PARAMETER/TYPE_USE nào.
5. Kiểm tra compilation/source đang dùng trong build hiện tại.
6. Nếu nghi vấn binary, xem class file bằng công cụ phù hợp.
7. Nếu runtime Reflection, thử query đúng AnnotatedElement.
8. Kiểm tra getAnnotation và getDeclaredAnnotation khác nhau thế nào.
9. Nếu repeatable, dùng getAnnotationsByType.
10. Nếu override, kiểm tra superclass/interface lookup policy.
11. Nếu generic, xem bridge/synthetic Method.
12. Nếu proxy, xác định Method từ interface hay implementation.
13. Kiểm tra class loader và module boundary.
14. Xác định engine có hỗ trợ join point cần chọn không.
15. Kiểm tra weaving đã áp dụng đúng class/time phase.
16. Nếu dùng metadata index, kiểm tra version và freshness.
17. Viết regression tests cho các đường ghi nhận và không ghi nhận.
18. Kiểm tra cache key/cached negative lookup khi build/runtime thay đổi.

Không vội đổi RetentionPolicy thành RUNTIME cho mọi annotation khi chưa biết consumer là compile-time tool hay binary weaver. Cần chọn đúng **nhu cầu đọc và giai đoạn đọc**.

## 40. Thiết kế annotation cho một module AOP có thể tái sử dụng

Một thiết kế annotation dùng cho runtime advice nên tự trả lời:

- Annotation này đánh dấu *loại phần tử nào*?
- Có cần runtime Reflection đọc không?
- Nó có thể lặp lại hay không?
- Giá trị mặc định của từng element là gì?
- Override method có được kế thừa logic hay không?
- Interface annotation được xử lý theo quy tắc nào?
- Có được đặt làm meta-annotation cho annotation khác không?
- Nếu có nhiều rules mâu thuẫn, precedence nào được áp dụng?
- Điểm can thiệp là call, execution, constructor hay loại khác?
- Có giới hạn package/class-loading nào không?
- Có thể cache resolution một lần theo class/version không?
- Có dữ liệu nhạy cảm nào không được đưa vào annotation values?

Một annotation tốt không chỉ biên dịch được; **hợp đồng diễn giải metadata cũng cần rõ** để advice behavior nhất quán qua nhiều modules và hình thức can thiệp.

## 41. Khi nào nên dùng metadata thay vì điều kiện runtime?

Metadata tĩnh phù hợp với những thông tin thay đổi rất ít theo invocation, như “method thuộc loại thao tác cần audit” hoặc “operation có category X”.

Điều kiện runtime phù hợp với dữ liệu mỗi lần gọi, như **giá trị tham số hiện tại**, actor đã xác thực hoặc kết quả tính toán.

Một aspect có thể kết hợp:

~~~text
Static selection:
    method is marked for observation

Runtime decision:
    current invocation has approved context
    and event policy allows emission
~~~

Nếu dữ liệu actor/tenant khác nhau theo request, không nên nhúng chúng như annotation values tĩnh trên method. Điều này vừa sai nghĩa vừa dễ rò thông tin qua metadata.

## 42. Một số câu hỏi tự kiểm tra

### Câu 1 — Retention mặc định

Annotation type không có @Retention. Reflection runtime có chắc đọc được không?

**Đáp án:** không. Mặc định retention CLASS, không phải RUNTIME.

### Câu 2 — Có trong class file nhưng không Reflection

Một annotation có retention CLASS. Có thể được binary weaver đọc không, và Method.getAnnotation có thấy không?

**Đáp án:** công cụ đọc class-file annotation attributes có thể thấy; Reflection runtime thông thường không trả annotation ấy.

### Câu 3 — Annotation trên kiểu trả về

@NonEmpty chỉ cho TYPE_USE và đặt trên return type. Nên hỏi Method.getAnnotation hay getAnnotatedReturnType?

**Đáp án:** getAnnotatedReturnType và API annotation trên AnnotatedType tương ứng.

### Câu 4 — Method override

Base.action có @Audit, Child.action override không khai báo annotation. @Inherited có tự copy annotation xuống Child.action không?

**Đáp án:** không. @Inherited áp dụng cho annotation on class trong phạm vi đặc tả, không tự cho method overrides.

### Câu 5 — Repeatables

Hai @Rule gắn cùng method. API nào phù hợp để lấy cả hai?

**Đáp án:** getAnnotationsByType(Rule.class), theo semantics repeatable.

### Câu 6 — Proxy

Interface method có annotation, implementation method không. Reflection trên implementation có tự thấy annotation của interface không?

**Đáp án:** không theo quy tắc tự động chung. Cần lookup policy hoặc khả năng được công cụ xác định.

### Câu 7 — SOURCE retention

Annotation SOURCE có thể có ích cho compile-time analysis không?

**Đáp án:** có, nếu compiler/processor thực sự có annotation ở giai đoạn xử lý thích hợp.

### Câu 8 — Parameter names

Biên dịch không có -parameters, Parameter.getName có chắc trả tên source thật không?

**Đáp án:** không. Có thể trả tên tổng hợp; phải kiểm tra isNamePresent.

### Câu 9 — Annotation type class loader

Hai annotation types cùng tên nhưng class loaders khác nhau có chắc là một type runtime không?

**Đáp án:** không. Type identity có class loader.

### Câu 10 — Cấu trúc và advice

Một method có @Observed và Reflection tìm thấy nó. Có chắc AOP engine sẽ advice method không?

**Đáp án:** không. Cần pointcut matching, weaving/interception coverage và runtime call path phù hợp.

### Câu 11 — Cache theo tên method

Nếu class có work(int) và work(String), cache annotation chỉ theo tên work có an toàn không?

**Đáp án:** không. Phải phân biệt chữ ký/descriptor.

### Câu 12 — Build-time index

Annotation index được tạo từ binary cũ, runtime nạp binary mới. Nguy cơ?

**Đáp án:** stale metadata có thể làm sai selection; cần versioning/rebuild/invalidation.

## 43. Checklist trước khi dùng annotation-based pointcut

- [ ] Đã khai báo đúng @Retention chưa?
- [ ] Consumer cần SOURCE, CLASS hay RUNTIME?
- [ ] @Target có đúng với vị trí thật sự dùng?
- [ ] Đọc đúng Class, Method, Field, Parameter hoặc AnnotatedType?
- [ ] Có xem xét @Inherited đúng giới hạn class-level?
- [ ] Có xử lý repeatable annotations với API phù hợp?
- [ ] Có quy tắc rõ cho interface và overriding?
- [ ] Có xét bridge/synthetic methods khi dùng generics?
- [ ] Đã phân biệt method call và method execution?
- [ ] Có xác minh class-file/weaving/runtime phase?
- [ ] Có xử lý đúng proxy và target method identity?
- [ ] Có class-loader-aware metadata lookup/cache?
- [ ] Có xử lý parameter names theo compiler flags?
- [ ] Có giới hạn metadata values nhạy cảm?
- [ ] Có tests riêng cho Reflection và AOP integration?
- [ ] Có test âm với annotation không tồn tại/retention thấp?
- [ ] Có test behavior khi nhiều annotations/giá trị mâu thuẫn?
- [ ] Có tài liệu hóa điều kiện và giới hạn của metadata matching?

## 44. Tổng kết

**Phạm vi lưu giữ** quyết định annotation còn tồn tại đến giai đoạn nào; **vị trí áp dụng** quyết định annotation gắn vào phần tử nào; **cơ chế đọc** quyết định công cụ có truy cập được metadata hay không.

Các nguyên tắc quan trọng nhất:

- **SOURCE:** hữu ích ở compile time, không còn như runtime annotation trong class file.
- **CLASS:** được giữ trong class file nhưng không hiển thị với Java Reflection thông thường.
- **RUNTIME:** cho phép Reflection truy vấn ở runtime khi chọn đúng phần tử.
- **Không có @Retention nghĩa là CLASS mặc định.**
- **@Target khác @Retention**, và METHOD khác TYPE_USE/PARAMETER.
- **@Inherited chỉ hỗ trợ ngữ nghĩa class-level cụ thể**, không tự sao chép annotation sang method override.
- **Repeatable annotations có container**, nên dùng API truy vấn đúng.
- **Interface, implementation, bridge, proxy và class loader** có thể làm metadata lookup khác nhau.
- **Annotation hiện diện không tự kích hoạt advice**; còn cần khả năng chọn/can thiệp join point.
- **Metadata tĩnh khác context động**, đặc biệt với request arguments và actor.
- **Reflection test và AOP integration test** bổ sung cho nhau, không thay thế nhau.

**Câu hỏi cuối cùng khi thiết kế một annotation-based aspect:** *Annotation được lưu tới đâu, tôi đang hỏi đúng phần tử và loại metadata nào, và cơ chế AOP thực tế có sử dụng được kết quả ấy tại đúng ranh giới can thiệp hay không?*
