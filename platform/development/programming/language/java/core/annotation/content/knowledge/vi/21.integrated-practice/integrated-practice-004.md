# Thực hành tổng hợp: So sánh kết quả khi thay đổi @Target, @Retention và @Inherited trong Java

## 1. Mục tiêu bài thực hành

Ba meta-annotation của Java thường xuất hiện cùng nhau trong định nghĩa một annotation type:

- `@Target`: annotation **được phép đặt ở những vị trí cú pháp nào**. Compiler kiểm tra khi biên dịch mã sử dụng annotation.
- `@Retention`: thông tin về **lần sử dụng annotation** được giữ đến giai đoạn nào: chỉ source, class file, hay có thể tra cứu bằng reflection lúc chạy.
- `@Inherited`: khi annotation type áp dụng trên **class**, Java reflection có thể nhìn thấy annotation từ **superclass** nếu class con chưa khai báo annotation cùng kiểu. Nó **không** tự áp dụng tương tự cho interface hoặc method override.

Ba câu hỏi độc lập nhưng có tương tác:

1. **Có được gắn ở đây không?** → `@Target`.
2. **Sau biên dịch có còn dữ liệu để quan sát không?** → `@Retention`.
3. **Khi đọc trên class con, có tính annotation của superclass không?** → `@Inherited` (và chỉ khi dữ liệu khả dụng cho cách đọc đó).

Mục tiêu là **thay đổi từng yếu tố trong điều kiện kiểm soát**, dự đoán kết quả rồi đối chiếu với `javac`, `java` và `javap`. Không nên thay đồng thời nhiều yếu tố ở lần thử đầu, bởi lỗi compile-time, thiếu metadata runtime và quy tắc kế thừa là những nguyên nhân khác nhau.

## 2. Bảng so sánh tổng quan

| Meta-annotation | Tác dụng chính | Quan sát lúc nào? | Nếu thay đổi |
| --- | --- | --- | --- |
| `@Target(TYPE)` | Chỉ cho phép annotation trên khai báo type phù hợp | `javac` kiểm tra vị trí đặt | Đặt lên method/field không thuộc target → lỗi biên dịch |
| `@Target({TYPE, FIELD, METHOD})` | Cho phép trên type, field, method | `javac` | Cùng một annotation có thể dùng ở nhiều cấp metadata |
| Không khai báo `@Target` | Có thể dùng trên các declaration contexts mà Java cho phép mặc định; không mặc nhiên mở mọi type-use | `javac` | Phạm vi cú pháp rộng hơn một target bị hạn chế |
| `@Retention(SOURCE)` | Lần sử dụng chỉ cần ở nguồn/compile time | Annotation processor/compiler | Không lưu lần dùng trong class file đích; reflection không thấy |
| `@Retention(CLASS)` | Giữ metadata trong class file | `javap -v`, bytecode reader | Reflection thông thường không thấy |
| `@Retention(RUNTIME)` | Giữ metadata và hỗ trợ reflection runtime | `Class/Field/Method.getAnnotation` | Có thể đọc khi tra đúng phần tử và annotation hiện diện |
| Không khai báo `@Retention` | Mặc định `CLASS` | Bytecode / runtime | Đừng mặc nhiên nghĩ runtime reflection đọc được |
| `@Inherited` | Cho phép tra annotation class từ superclass khi đủ điều kiện | Reflection trên `Class` | Class con có thể đọc annotation của superclass |
| Không có `@Inherited` | Không áp dụng cơ chế inheritance đặc biệt | Reflection trên `Class` | `Child.class.getAnnotation(T.class)` không nhận T chỉ có ở cha |

**Cần nhớ:** `@Target` **không** quyết định lifetime của metadata. `@Retention` **không** cho phép đặt annotation ở vị trí target không hợp lệ. `@Inherited` **không** khiến metadata tự lan sang mọi thành viên hoặc interface. Chúng là ba chiều của một hợp đồng annotation.

## 3. Thiết kế thí nghiệm: chỉ thay một biến

Để kiểm tra có kiểm soát, sử dụng ba nhóm fixture:

- **Nhóm A – Target:** đặt cùng một annotation trên class, field, method, constructor; thay đổi danh sách `ElementType` và quan sát trường hợp `javac` chấp nhận/từ chối.
- **Nhóm B – Retention:** gắn ba annotation có cùng `@Target` nhưng lần lượt `SOURCE`, `CLASS`, `RUNTIME`; quan sát class file bằng `javap` rồi so với kết quả reflection.
- **Nhóm C – Inherited:** gắn annotation runtime lên superclass, tạo subclass không khai báo annotation, subclass có annotation riêng, interface được đánh dấu và method bị override; so sánh `getAnnotation` với `getDeclaredAnnotation`.

Ở phần chương trình độc lập bên dưới, một lần biên dịch Java 17 sẽ bao phủ nhóm B và C, đồng thời cung cấp ví dụ target hợp lệ. Những mã **cố ý sai** để thử Target được tách riêng; không đặt mã không biên dịch được vào chương trình chính.

## 4. @Target: thay vị trí đặt annotation có thể đổi kết quả biên dịch

Giả sử định nghĩa:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface TypeLabel {}
~~~

`@Target(ElementType.TYPE)` có nghĩa annotation được dùng trên **khai báo kiểu** phù hợp, ví dụ class hoặc interface. Với mã minh họa:

~~~java
@TypeLabel
class Catalog {}

@TypeLabel
interface Marker {}
~~~

Hai vị trí trên hợp lệ. Nhưng cố gắn vào field:

~~~java
class Catalog {
    @TypeLabel
    private int count;
}
~~~

là **ví dụ cố ý không biên dịch**: annotation type `TypeLabel` không áp dụng cho field. Khi gắn vào method hay constructor cũng không hợp lệ nếu target chỉ là `TYPE`.

Để cho phép nhiều vị trí, sửa định nghĩa:

~~~java
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.CONSTRUCTOR
})
@interface Label {}
~~~

Khi đó có thể đặt cùng `@Label` lên class, field, method và constructor theo đúng cú pháp Java.

### 4.1. Khi đổi Target, điều gì không đổi?

Nếu `@Label` vẫn có retention `RUNTIME`, việc mở rộng `@Target` từ `TYPE` sang `{TYPE, FIELD, METHOD}` không tự đổi retention của annotation, không sao chép annotation trên class sang field/method, và cũng không làm JVM tự xử lý metadata. Nó **chỉ** cho phép viết thêm những chỗ gắn annotation mới hợp lệ.

Ngược lại, thu hẹp `@Target` khiến **source mới** gắn annotation ở vị trí bị loại báo lỗi khi biên dịch. Class file cũ không tự được viết lại; nếu đã phát hành annotation như thư viện, phải đánh giá việc sửa Target như một thay đổi hợp đồng với tất cả nơi dùng.

### 4.2. TYPE, TYPE_USE, TYPE_PARAMETER và PARAMETER không giống nhau

Ba cặp dễ nhầm:

| ElementType | Vị trí được chú thích | Ví dụ |
| --- | --- | --- |
| `TYPE` | Khai báo class/interface/enum/annotation type/record phù hợp | `@Label class Catalog {}` |
| `FIELD` | Khai báo field | `@Label int size;` |
| `METHOD` | Khai báo method | `@Label void run() {}` |
| `CONSTRUCTOR` | Khai báo constructor | `@Label Catalog() {}` |
| `PARAMETER` | Khai báo parameter của method/constructor | `void run(@Label String arg) {}` |
| `TYPE_PARAMETER` | Khai báo tham số kiểu generic | `class Box<@Label T> {}` |
| `TYPE_USE` | Một vị trí sử dụng kiểu | `List<@Label String> names;` |
| `PACKAGE` | Khai báo package | `package-info.java` |
| `MODULE` | Khai báo JPMS module | `module-info.java` |

Các ví dụ trong bảng là **cú pháp minh họa**; muốn biên dịch phải định nghĩa `Label` với target tương ứng và cung cấp những type/import cần thiết.

Annotation đặt trên **khai báo field** không đồng nghĩa annotation gắn trên **generic type argument**. `@Target(TYPE_USE)` là một khái niệm khác `@Target(TYPE)`. Reflection cũng có những API khác nhau: `Field.getAnnotation(...)` đọc declaration annotation, còn `Field.getAnnotatedType()` và các API `AnnotatedType` đọc type-use metadata thích hợp.

### 4.3. Thiếu @Target có nghĩa gì?

Khi không khai báo `@Target`, Java cho phép annotation trên các loại **declaration** được quy định mặc định. Điều này không có nghĩa annotation tự hợp lệ ở mọi chỗ trong cú pháp Java hoặc tự chấp nhận mọi `TYPE_USE`. Nếu metadata có phạm vi rõ, khai báo target tường minh giúp compiler ngăn sai sót sớm.

## 5. @Retention: SOURCE, CLASS, RUNTIME có dấu vết khác nhau

Với cùng target:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeMark {}
~~~

Mỗi annotation đều **có thể gắn** lên class. Nhưng compiler xử lý **lần sử dụng annotation** theo retention:

- **SOURCE:** annotation processor hoặc compiler có thể thấy trong lúc biên dịch source; trong class file của class được đánh dấu không có metadata của lần dùng annotation đó.
- **CLASS:** thông tin vẫn được ghi trong class file của phần tử được đánh dấu; với annotation trên declaration thường nằm trong `RuntimeInvisibleAnnotations`. Java reflection thông thường **không** cung cấp nó.
- **RUNTIME:** thông tin còn trong class file và có thể đọc bằng reflection thông thường trên đúng `AnnotatedElement`; với annotation trên declaration thường nằm trong `RuntimeVisibleAnnotations`.

Từ “invisible” không có nghĩa bytecode reader không nhìn thấy. `javap -v` có thể hiển thị cả `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations`.

**Lưu ý tinh tế:** compiler có thể tạo class file cho **định nghĩa annotation type** `SourceMark`. `SOURCE` nói về việc giữ **lần sử dụng @SourceMark trên phần tử đích**, không phải việc xóa hoàn toàn class file của chính annotation type khỏi kết quả biên dịch.

### 5.1. Nếu đổi Retention từ RUNTIME sang CLASS

Giả sử `@State("ready")` được đọc qua:

~~~java
State state = Catalog.class.getAnnotation(State.class);
~~~

Đoạn này là minh họa, giả định `State` đã tồn tại. Nếu source của `Catalog` được **biên dịch lại** khi `State` đã chuyển sang `Retention(CLASS)`, phản chiếu runtime không còn thấy annotation như trước. Nếu chỉ thay định nghĩa annotation trong một JAR mà giữ nguyên **class file cũ** từng được biên dịch với retention `RUNTIME`, không thể khẳng định file cũ tự bị viết lại. Khi kiểm tra thay đổi retention, phải kiểm tra **bytecode thực sự đang được chạy** và biên dịch lại các lần dùng cần so sánh.

### 5.2. @Retention và thời điểm xử lý

`Retention(SOURCE)` hoàn toàn có thể phục vụ **annotation processor** ở compile time. `Retention(CLASS)` có thể phục vụ **bytecode analysis**. `Retention(RUNTIME)` phục vụ reflection hoặc framework hoạt động runtime. Không có chính sách nào tự ra lệnh JVM gọi một method chỉ vì annotation tồn tại.

Nếu yêu cầu nghiệp vụ là annotation runtime điều khiển validation, routing hoặc phân quyền, phải có **component tiêu thụ và áp dụng quy tắc**. Thay `Retention` mà không thay công cụ đọc có thể khiến hệ thống không thấy metadata hoặc hiểu sai cấu hình.

## 6. @Inherited: không phải kế thừa Java member thông thường

Khai báo:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface FamilyLabel {
    String value();
}
~~~

Với:

~~~java
@FamilyLabel("parent")
class Base {}

class Child extends Base {}
~~~

thì `Child.class.getAnnotation(FamilyLabel.class)` có thể trả annotation từ `Base`, vì:

1. `FamilyLabel` có `@Inherited`.
2. Annotation được gắn trên một **class declaration** (`Base`).
3. `Child` là **subclass** trong chuỗi superclass, không phải chỉ là class implement interface.
4. Metadata có retention `RUNTIME` nên reflection có thể đọc được.

Trong khi đó:

~~~java
Child.class.getDeclaredAnnotation(FamilyLabel.class)
~~~

trả `null` nếu chính `Child` không khai báo annotation. Từ `Declared` có nghĩa **chỉ xét khai báo tại phần tử đó**, không tự tra superclass.

### 6.1. Class con tự khai báo thì sao?

Nếu:

~~~java
@FamilyLabel("child")
class Child extends Base {}
~~~

`Child.class.getAnnotation(FamilyLabel.class).value()` trả `"child"`. Annotation trực tiếp trên child quyết định kết quả cho kiểu đó, thay vì bắt buộc đọc giá trị của parent.

Điều này không có nghĩa Java tự **hợp nhất** giá trị annotation trên tất cả superclass. Với repeatable annotations, các API `getAnnotationsByType` có quy tắc chuyên biệt. Nếu nghiệp vụ cần cộng dồn metadata nhiều tầng, cần viết logic duyệt lớp cha và xử lý kết hợp một cách rõ ràng.

### 6.2. Interface không truyền @Inherited vào class implement

Ví dụ:

~~~java
@FamilyLabel("interface")
interface Contract {}

class ContractImpl implements Contract {}
~~~

`ContractImpl.class.getAnnotation(FamilyLabel.class)` **không** tự nhìn thấy `@FamilyLabel("interface")` trên `Contract`. `@Inherited` được thiết kế cho việc tra annotation **trên class qua superclass**, không duyệt qua tất cả interfaces mà class implement.

Một framework có thể chủ động tìm metadata trên interfaces, nhưng đó là quy tắc riêng của framework, không phải kết quả mặc định của `Class.getAnnotation`.

### 6.3. Method override không tự nhận annotation của method cha

Kể cả khi annotation type đánh dấu `@Inherited` và target `METHOD`:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

class Base {
    @MethodMark
    public void process() {}
}

class Child extends Base {
    @Override
    public void process() {}
}
~~~

`Child.class.getDeclaredMethod("process").getAnnotation(MethodMark.class)` trả `null`. Lý do là `@Inherited` không thiết lập việc kế thừa metadata cho **method**. Java method overriding và cơ chế reflection của annotation declaration là hai vấn đề khác nhau.

Tương tự, field và constructor không tự sao chép annotation từ những khai báo ở class cha. Constructor thậm chí **không được kế thừa** như method. Nếu dùng `Child.class.getMethod("process")` khi child **không override**, bạn có thể lấy đối tượng `Method` của phương thức được kế thừa từ parent; kết quả đọc annotation khi đó thuộc về method **trên parent**, không phải cơ chế `@Inherited` của annotation trên method con.

### 6.4. @Inherited có tác dụng nếu Retention không phải RUNTIME?

`@Inherited` chỉ quy định quy tắc **tra cứu annotation class** trong mô hình ngôn ngữ/reflection phù hợp. Nếu annotation type có retention `SOURCE` hoặc `CLASS`, API reflection thông thường lúc chạy không thấy lần dùng annotation trên class, nên `@Inherited` không thể khiến metadata đã không có trong reflection “xuất hiện trở lại”. Hai điều kiện cần phối hợp khi muốn đọc annotation kế thừa ở runtime là **`@Inherited` và `@Retention(RUNTIME)`**.

## 7. Chương trình Java 17+ độc lập: kiểm chứng tất cả kết luận cốt lõi

Tạo một file duy nhất tên **`AnnotationMetaComparisonDemo.java`** chứa các annotation type và class kiểm thử sau. File dùng package mặc định để dễ chạy thí nghiệm bằng terminal; dự án thật thường đặt trong named package.

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@interface RuntimeMark { String value(); }

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface FamilyLabel { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface LocalLabel { String value(); }

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface MethodMark {}

@SourceMark
@ClassMark
@RuntimeMark("base")
@FamilyLabel("parent")
@LocalLabel("direct-only")
class BaseService {
    @SourceMark @ClassMark @RuntimeMark("field")
    private int count;

    @SourceMark @ClassMark @RuntimeMark("method") @MethodMark
    public void process() {}
}

class ChildService extends BaseService {
    @Override public void process() {}
}

@FamilyLabel("interface")
interface ServiceContract {}
class InterfaceImpl implements ServiceContract {}

@FamilyLabel("child")
class OverridingChild extends BaseService {}

public class AnnotationMetaComparisonDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<BaseService> base = BaseService.class;
        Class<ChildService> child = ChildService.class;

        System.out.println("source-visible="
                + base.isAnnotationPresent(SourceMark.class));
        System.out.println("class-visible="
                + base.isAnnotationPresent(ClassMark.class));
        System.out.println("runtime-base="
                + base.getAnnotation(RuntimeMark.class).value());
        System.out.println("runtime-field="
                + base.getDeclaredField("count")
                      .getAnnotation(RuntimeMark.class).value());
        System.out.println("runtime-method="
                + base.getDeclaredMethod("process")
                      .getAnnotation(RuntimeMark.class).value());

        System.out.println("child-family="
                + child.getAnnotation(FamilyLabel.class).value());
        System.out.println("child-local-label="
                + child.isAnnotationPresent(LocalLabel.class));
        System.out.println("child-declared-lookup="
                + (child.getDeclaredAnnotation(FamilyLabel.class) != null));
        System.out.println("child-runtime="
                + (child.getAnnotation(RuntimeMark.class) != null));
        System.out.println("interface-inherited="
                + (InterfaceImpl.class.getAnnotation(FamilyLabel.class) != null));

        Method override = child.getDeclaredMethod("process");
        System.out.println("method-inherited="
                + (override.getAnnotation(MethodMark.class) != null));
        System.out.println("child-own-family="
                + OverridingChild.class.getAnnotation(FamilyLabel.class).value());
    }
}
~~~

### 7.1. Biên dịch và chạy

Đứng ở thư mục chứa file trên, sử dụng **JDK 17 trở lên**:

~~~bash
javac --release 17 AnnotationMetaComparisonDemo.java
java AnnotationMetaComparisonDemo
~~~

**Stdout chính xác:**

~~~text
source-visible=false
class-visible=false
runtime-base=base
runtime-field=field
runtime-method=method
child-family=parent
child-local-label=false
child-declared-lookup=false
child-runtime=false
interface-inherited=false
method-inherited=false
child-own-family=child
~~~

Chương trình đã được **biên dịch với `javac --release 17` và thực thi** trên JDK tương thích Java 17; kết quả trên khớp stdout của chương trình.

### 7.2. Phân tích từ đầu đến cuối

- `source-visible=false`: `@SourceMark` chỉ dành cho compile time, không được `Class.isAnnotationPresent` phát hiện lúc chạy.
- `class-visible=false`: `@ClassMark` vẫn có thể nằm trong class file của `BaseService` nhưng không được reflection thông thường cung cấp.
- `runtime-base=base`: `@RuntimeMark("base")` được đánh dấu `RUNTIME` và đặt trực tiếp trên class.
- `runtime-field=field`: lần dùng annotation khác được gắn vào khai báo field `count`. Phải lấy đúng `Field`.
- `runtime-method=method`: tương tự, phải lấy đúng `Method` khai báo ở parent.
- `child-family=parent`: `@FamilyLabel` có `@Inherited`, nên `ChildService` nhìn thấy annotation của `BaseService`.
- `child-local-label=false`: `@LocalLabel` cũng có retention `RUNTIME` nhưng **không có @Inherited**, do đó class con không thấy nó.
- `child-declared-lookup=false`: `ChildService` không khai báo `FamilyLabel` trực tiếp. `getDeclaredAnnotation` không tự tìm superclass.
- `child-runtime=false`: `@RuntimeMark` không được đánh dấu `@Inherited`; chỉ vì nó có retention `RUNTIME` không có nghĩa nó xuất hiện trên class con.
- `interface-inherited=false`: annotation trên interface không được class implement nhận thông qua `@Inherited`.
- `method-inherited=false`: `@MethodMark` có `@Inherited` nhưng đặt trên method, không tạo cơ chế kế thừa annotation khi method bị override.
- `child-own-family=child`: class con có `@FamilyLabel("child")` trực tiếp nên kết quả không lấy `"parent"` từ superclass.

**Một chi tiết kiểm thử quan trọng:** những dòng in `false` là kết quả quan sát có điều kiện xác định. Đừng suy luận từ chúng rằng compiler không thể thấy SOURCE annotation, CLASS annotation đã biến mất khỏi bytecode, hoặc interface không được JVM hỗ trợ.

## 8. Dùng javap xác nhận CLASS retention vẫn tồn tại

Sau khi biên dịch chương trình chính, chạy:

~~~bash
javap -v BaseService
~~~

Dùng `javap -v` để quan sát class file của **class được đánh dấu**, không chỉ class file của chính annotation type.

Trong output verbose, bạn sẽ thấy thông tin tương tự:

~~~text
RuntimeVisibleAnnotations:
  RuntimeMark(...)
  FamilyLabel(...)
  LocalLabel(...)

RuntimeInvisibleAnnotations:
  ClassMark
~~~

Đây là **mẫu trình bày giản lược**, không phải stdout nguyên văn của `javap`. Bản gốc có indices từ constant pool, descriptors và metadata khác.

Ở mức class declaration:

- `@RuntimeMark`, `@FamilyLabel`, `@LocalLabel` xuất hiện trong `RuntimeVisibleAnnotations`.
- `@ClassMark` nằm trong `RuntimeInvisibleAnnotations`.
- `@SourceMark` **không** có annotation entry trên class `BaseService` vì retention là `SOURCE`.

Trong `BaseService.class`, các field/method được đánh dấu cũng có vùng attribute tương ứng của chính chúng; không nên gộp metadata class với metadata method/field khi đọc output `javap`. Hai loại `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations` là các chi tiết của **class-file format**, còn `RetentionPolicy` là cách khai báo chính sách trong source.

## 9. Thực hành thay đổi từng meta-annotation và dự đoán kết quả

Thực hiện lần lượt; mỗi lần **sửa source, biên dịch lại**, không làm đồng thời nhiều thay đổi. Các dòng dự đoán dưới đây giả sử các dòng code liên quan vẫn đúng như chương trình chính trừ thay đổi được nêu.

### Thử nghiệm A1 — thu hẹp Target của RuntimeMark

Đổi:

~~~java
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
~~~

ở `RuntimeMark` thành:

~~~java
@Target(ElementType.TYPE)
~~~

**Dự đoán:** `javac` báo lỗi ở `@RuntimeMark("field")` và `@RuntimeMark("method")`, vì annotation này không còn áp dụng cho field và method. Lỗi xuất hiện **trước runtime**; không có stdout từ chương trình đã biên dịch mới nếu chỉ dùng source lỗi.

**Sửa:** hoặc mở rộng target trở lại, hoặc bỏ hai lần gắn trên field/method. Nếu bỏ chúng nhưng giữ code gọi `getAnnotation(RuntimeMark.class).value()` trên field/method, cần cập nhật code để kiểm tra `null` tránh `NullPointerException`.

### Thử nghiệm A2 — mở rộng Target thay vì đổi Retention

Giữ `@Retention(RUNTIME)` của `RuntimeMark`, bổ sung `ElementType.CONSTRUCTOR` vào `@Target` rồi thêm một constructor tường minh có `@RuntimeMark("ctor")` vào `BaseService`.

**Dự đoán:** compiler cho phép. Khi lấy đúng `Constructor<?>` và đọc `getAnnotation(RuntimeMark.class)`, thấy giá trị `"ctor"`. Kết quả trên class, field, method **không tự thay đổi** do mở rộng target. Annotation trên constructor cũng không được tự truyền vào class hoặc method.

### Thử nghiệm B1 — đổi RUNTIME thành CLASS

Chỉ đổi `@Retention(RetentionPolicy.RUNTIME)` trên `RuntimeMark` thành:

~~~java
@Retention(RetentionPolicy.CLASS)
~~~

Giữ các `@RuntimeMark` trên class, field, method. **Dự đoán:** sau khi biên dịch lại, metadata của các lần dùng `RuntimeMark` được ghi vào class file theo retention CLASS nhưng không thấy qua reflection. Nếu chạy **nguyên chương trình** với những lệnh `getAnnotation(...).value()` thì có thể ném `NullPointerException` ở dòng đọc `runtime-base` vì `getAnnotation(RuntimeMark.class)` trả `null`. Để xem đầy đủ kết quả mới, hãy sửa chương trình thử nghiệm thành các kiểm tra an toàn như:

~~~java
System.out.println(
    BaseService.class.isAnnotationPresent(RuntimeMark.class)); // false
~~~

Đừng kết luận `@RuntimeMark` đã mất khỏi class file chỉ từ `false`. Dùng `javap -v BaseService` để thấy thông tin trong `RuntimeInvisibleAnnotations`.

### Thử nghiệm B2 — đổi CLASS thành SOURCE

Đổi `@Retention(CLASS)` trên `ClassMark` sang `SOURCE`, biên dịch lại rồi dùng `javap -v BaseService`.

**Dự đoán:** những lần dùng `@ClassMark` không còn được lưu trong class file đích. Reflection vẫn là `false` như trước. Đây là một ví dụ cho thấy **hai cấu hình khác nhau có thể cho cùng kết quả reflection nhưng khác bytecode**.

### Thử nghiệm B3 — đổi CLASS thành RUNTIME

Đổi `@Retention(CLASS)` trên `ClassMark` sang `RUNTIME` và biên dịch lại.

**Dự đoán:** `BaseService.class.isAnnotationPresent(ClassMark.class)` chuyển từ `false` sang `true`; annotation cũng có thể đọc từ field và method tương ứng. Trong `javap -v`, lần dùng `ClassMark` nằm ở nhóm visible thay vì invisible. `@Target` của nó vẫn không đổi.

### Thử nghiệm C1 — bỏ @Inherited khỏi FamilyLabel

Giữ `RUNTIME` nhưng bỏ dòng `@Inherited` trên `FamilyLabel`, biên dịch lại chương trình. Khi chạy **nguyên code**, `child.getAnnotation(FamilyLabel.class)` sẽ trả `null`, vì vậy lời gọi `.value()` ở sau có thể gây `NullPointerException`.

Để quan sát không bị crash, đổi riêng dòng in thành:

~~~java
System.out.println(
    ChildService.class.getAnnotation(FamilyLabel.class) != null);
~~~

**Dự đoán:** in `false`. Trong khi đó `BaseService.class.getAnnotation(FamilyLabel.class)` vẫn đọc được giá trị `"parent"` vì annotation vẫn trực tiếp trên class cha và có retention `RUNTIME`. Bỏ `@Inherited` không xóa annotation trên chính parent.

### Thử nghiệm C2 — giữ Inherited nhưng đổi Retention thành CLASS

Giữ `@Inherited` trên `FamilyLabel` nhưng đổi retention từ `RUNTIME` sang `CLASS`; biên dịch lại. `ChildService.class.getAnnotation(FamilyLabel.class)` không thấy annotation ở runtime vì metadata trên `BaseService` không được reflection cung cấp. `@Inherited` không thể bù cho retention không phù hợp.

### Thử nghiệm C3 — thêm FamilyLabel trực tiếp trên ChildService

Giữ `@Inherited` và `RUNTIME`; thêm:

~~~java
@FamilyLabel("child-direct")
class ChildService extends BaseService {
    @Override public void process() {}
}
~~~

**Dự đoán:** `ChildService.class.getAnnotation(FamilyLabel.class).value()` trả `"child-direct"`. Đồng thời `ChildService.class.getDeclaredAnnotation(FamilyLabel.class)` không còn `null`, vì annotation đã được khai báo trực tiếp tại child.

### Thử nghiệm C4 — đánh dấu interface

Giữ `@Inherited`, `RUNTIME` trên `FamilyLabel`. Dù interface `ServiceContract` có `@FamilyLabel("interface")`, `InterfaceImpl.class.getAnnotation(FamilyLabel.class)` vẫn trả `null` nếu `InterfaceImpl` không được đánh dấu trực tiếp và không nhận annotation từ một superclass phù hợp.

### Thử nghiệm C5 — đánh dấu method bằng @Inherited

Trong chương trình chính đã có `@Inherited` trên annotation type `MethodMark` và `@MethodMark` trên method `BaseService.process()`. `ChildService.process()` override mà không khai báo `@MethodMark` nên tra trên method override là `null`. Đổi Target của `MethodMark` để gồm `TYPE` có thể cho phép annotation này cũng gắn lên class, nhưng **không** làm method override tự nhận annotation của method cha.

## 10. Ma trận kết quả dự đoán (nhìn nhanh)

Bảng sau xét trường hợp annotation được gắn **trực tiếp trên Base**, class `Child extends Base` không có annotation cùng kiểu, và runtime code dùng `Class.getAnnotation(T.class)`. Các tình huống target không cho phép gắn trên class bị loại từ đầu.

| Target cho phép TYPE? | Retention | Có @Inherited? | Annotation trên Base có đọc được qua reflection? | Child có thấy annotation Base qua `getAnnotation`? |
| --- | --- | --- | --- | --- |
| Có | `SOURCE` | Không | Không | Không |
| Có | `SOURCE` | Có | Không | Không |
| Có | `CLASS` | Không | Không | Không |
| Có | `CLASS` | Có | Không | Không |
| Có | `RUNTIME` | Không | Có | Không |
| Có | `RUNTIME` | Có | Có | **Có** |
| Không | Bất kỳ | Bất kỳ | **Không được gắn lên Base từ source mới** | Không có trường hợp nguồn hợp lệ để kiểm tra kế thừa theo giả định |

Điều kiện bổ sung: annotation phải nằm trên **class declaration**, không phải interface hay method; source/class file phải được biên dịch theo các định nghĩa annotation type tương thích với cấu hình đang thử. `getDeclaredAnnotation` trên Child sẽ **không** tìm parent ở mọi dòng của bảng. Nếu Child tự gắn annotation T, hãy xét annotation trực tiếp trên Child trước thay vì áp dụng bảng dành cho Child trống.

Đây là một cách đánh giá nhanh: nếu muốn annotation **đọc được từ subclass bằng runtime reflection**, thiết kế tối thiểu thường gồm:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DomainLabel {}
~~~

Tất nhiên tên và target thực tế phải phản ánh ý nghĩa nghiệp vụ; không tự thêm `@Inherited` chỉ vì muốn dễ lấy metadata nếu bạn không muốn chính sách class cha áp dụng cho class con.

## 11. Quy tắc getAnnotation và getDeclaredAnnotation trong thí nghiệm

Cần phân biệt ba câu hỏi:

1. **Phần tử này có khai báo annotation trực tiếp không?** Dùng `getDeclaredAnnotation(T.class)`.
2. **Annotation T có được coi là hiện diện tại phần tử không?** Dùng `getAnnotation(T.class)`; với `Class`, nếu T là inherited và điều kiện phù hợp, có thể đọc superclass.
3. **Có nhiều lần dùng T được phép lặp không?** Dùng `getAnnotationsByType(T.class)` hoặc `getDeclaredAnnotationsByType(T.class)` để xử lý `@Repeatable` và annotation container.

Đừng dùng `getAnnotation(T.class) == null` để kết luận “không có lần dùng T nào” khi T là repeatable và có các phần tử trong container: API đơn lẻ không tự bung container. Trong bài thực hành chính, các annotation không phải repeatable nên vấn đề này không làm thay đổi stdout.

**Lưu ý:** `@Inherited` áp dụng theo quy tắc tra cứu trên **Class**, không áp dụng kiểu “mọi khai báo được Java kế thừa đều kế thừa metadata”. Một method của superclass được tìm qua `getMethod` có thể khiến bạn đang đọc chính method của superclass, chứ không phải annotation được Java tự sao chép sang method override của subclass.

## 12. Các sai lầm thường gặp khi so sánh ba meta-annotation

| Ngộ nhận | Thực tế |
| --- | --- |
| “`@Target(TYPE)` làm annotation lưu trong class file” | Target chỉ giới hạn vị trí; Retention mới quyết định có giữ dữ liệu đến class file hay không |
| “`@Retention(RUNTIME)` có nghĩa annotation tự có hiệu lực” | Nó chỉ hỗ trợ runtime access; cần code/framework thật sự xử lý metadata |
| “`@Inherited` giúp annotation SOURCE hiện ở runtime” | Không; metadata SOURCE không tồn tại ở runtime reflection |
| “CLASS và SOURCE như nhau vì đều trả false khi reflection” | Sai; CLASS còn lưu trong bytecode, SOURCE không |
| “`@Inherited` làm interface annotation truyền sang class implement” | Không; inheritance chuẩn này theo superclass class |
| “Method override tự kế thừa annotation method cha” | Không, ngay cả khi annotation type có `@Inherited` |
| “`getDeclaredAnnotation` cũng lấy annotation ở cha” | Không; Declared chỉ trên phần tử hiện tại |
| “Mở rộng Target sẽ tự thêm annotation vào tất cả member mới” | Không; nó chỉ mở rộng nơi có thể viết annotation trong source |
| “Một annotation gắn trên class sẽ được thấy khi đọc Field.getAnnotation” | Không; cần annotation thực sự gắn vào field |
| “Đổi retention trong JAR là class file đã biên dịch cũ tự đổi attribute” | Không; cần quan sát bytecode và biên dịch lại annotated source để thử thay đổi theo contract mới |
| “Nếu compiler từ chối @Target thì JVM bị lỗi khi chạy” | Không có class file mới hợp lệ cho nguồn sai; lỗi xảy ra ngay lúc biên dịch |
| “@Inherited là bắt buộc với mọi annotation” | Không; chỉ sử dụng khi ngữ nghĩa metadata trên class được thiết kế để áp dụng cho subclass |

Một dấu hiệu kiểm tra sai là dựa vào kết quả `false` đơn lẻ. Khi nhận `false`, cần xác định đây là **không có metadata tại runtime**, **chỉ không kế thừa**, **đang đọc sai vị trí**, hoặc **không có annotation trực tiếp**.

## 13. Cách kiểm thử trong dự án có framework

Ví dụ một hệ thống dùng `@RequiresPermission` trên class, muốn subclass tự nhận chính sách của parent. Khi thêm `@Inherited` và `@Retention(RUNTIME)`, những component dùng `Class.getAnnotation(RequiresPermission.class)` có thể nhận annotation từ superclass phù hợp. Tuy nhiên:

- Framework có thể dùng API `getDeclaredAnnotations()` và **không** nhận metadata kế thừa dù annotation type có `@Inherited`.
- Framework có thể tự duyệt interface, method overrides hoặc container annotations theo chính sách riêng, **không phụ thuộc** quy tắc reflection chuẩn.
- `@Target(TYPE)` cho phép gắn trên class, nhưng việc truyền chính sách từ class tới method có hay không do framework quyết định.
- Một chính sách bảo mật nên có tài liệu và test rõ **lúc nào superclass policy áp dụng**, **lúc nào child override**, **có hợp nhất hay không** và **hành vi khi metadata vắng mặt**. Không dựa riêng vào meta-annotation để khẳng định authorization được bảo vệ.

Do vậy, khi so sánh kết quả thực tế, hãy kiểm tra cả **contract của Java** và **contract của framework consumer**. Java reflection cho một số quy tắc mặc định, framework có thể áp dụng quy tắc khác.

## 14. Checklist chấm kết quả bài thực hành

Bạn hoàn thành bài khi có thể:

- [ ] Dự đoán target hợp lệ/không hợp lệ cho class, field, method, constructor, parameter và type-use.
- [ ] Giải thích vì sao mã gắn annotation sai target **không biên dịch**, không cần chạy.
- [ ] Nói rõ default của `@Retention` là `CLASS` và không có `@Target` không đồng nghĩa hỗ trợ mọi type-use.
- [ ] Biên dịch chương trình Java 17, đối chiếu stdout SOURCE/CLASS/RUNTIME với reflection.
- [ ] Dùng `javap -v BaseService` xác minh CLASS còn trong class file dù reflection trả `false`.
- [ ] Giải thích sự khác nhau giữa đọc metadata trên class, field và method.
- [ ] Dự đoán `getAnnotation` và `getDeclaredAnnotation` trên Child khi `@Inherited` được bật/tắt.
- [ ] Chỉ ra vì sao annotation trên interface không được class implement nhận bằng cơ chế `@Inherited`.
- [ ] Chỉ ra vì sao annotation trên method của superclass không tự truyền sang method override.
- [ ] Dự đoán kết quả khi subclass trực tiếp khai báo một annotation cùng kiểu với superclass.
- [ ] Không thay đồng thời Target, Retention, Inherited trong một lần thử nếu mục tiêu là xác định nguyên nhân.
- [ ] Khi thay phiên bản annotation library, phân biệt class file cũ với class file đã biên dịch lại.
- [ ] Nếu annotation điều khiển framework, xác định **bộ tiêu thụ** và test cả logic framework, không chỉ reflection.

**Ghi nhớ:** `@Target` quyết định **chỗ được gắn**, `@Retention` quyết định **mức độ lưu metadata**, còn `@Inherited` điều chỉnh **cách reflection tra annotation trên class con từ superclass**. Thay đổi từng meta-annotation có thể dẫn đến **lỗi biên dịch**, **khác biệt class file/reflection**, hoặc **khác biệt tra cứu kế thừa** — ba loại kết quả này phải được đánh giá riêng, rồi mới kết hợp trong một thiết kế annotation hoàn chỉnh.
