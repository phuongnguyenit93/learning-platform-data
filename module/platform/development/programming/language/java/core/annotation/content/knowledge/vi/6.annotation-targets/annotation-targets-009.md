# Không khai báo @Target, @Target({}) và lỗi đặt annotation sai vị trí trong Java

Trong Java, một annotation có thể hợp lệ trên lớp nhưng bị trình biên dịch từ chối khi đặt lên field, method hoặc một kiểu đang được sử dụng. Quy tắc đó đến từ **`java.lang.annotation.Target`** và các giá trị **`ElementType`**. Đặc biệt, hai cách khai báo nhìn gần giống nhau dưới đây lại mang nghĩa hoàn toàn khác:

~~~java
@interface OpenMarker {}                 // Không có @Target.

@java.lang.annotation.Target({})
@interface NestedOnly {}                // Có @Target với danh sách rỗng.
~~~

- **Không khai báo `@Target`**: annotation áp dụng được ở **mọi declaration context** theo đặc tả Java hiện đại; nhưng **không áp dụng ở type context** chỉ nhờ việc thiếu `@Target`.
- **`@Target({})`**: annotation **không áp dụng trực tiếp được ở bất kỳ declaration context hay type context nào**. Trường hợp hữu ích là làm giá trị annotation lồng trong một annotation khác.
- **`@Target(ElementType.XXX)`**: giới hạn rõ các vị trí được phép; Java compiler kiểm tra chỗ gắn annotation và báo lỗi biên dịch nếu không hợp lệ.

Ba trường hợp này cần phân biệt với **`@Retention`**. `@Target` điều khiển **nơi được phép viết**; `@Retention` điều khiển **annotation được lưu đến giai đoạn nào**. Đặt `@Retention(RUNTIME)` không tự mở rộng vị trí hợp lệ.

## 1. Những ngữ cảnh mà @Target kiểm soát

Java phân loại chỗ đặt annotation thành hai nhóm chính.

**Declaration context** là nơi một thành phần chương trình được **khai báo**: lớp, interface, field, method, constructor, tham số, biến cục bộ, tham số kiểu generic, package, module, record component, v.v.

**Type context** là nơi một **kiểu được sử dụng** trong khai báo hoặc biểu thức: kiểu ở `extends`, `implements`, kiểu của biểu thức `new`, kiểu trong cast, generic type argument, thành phần kiểu mảng, v.v. Các chỗ này thường dùng annotation với `ElementType.TYPE_USE`.

Một số hằng `ElementType` hay gặp:

| ElementType | Mục đích | Ví dụ chỗ gắn |
| --- | --- | --- |
| `TYPE` | Khai báo class, interface, enum, record và annotation interface | `@Flag class Order {}` |
| `ANNOTATION_TYPE` | Khai báo annotation interface | `@Flag @interface Meta {}` |
| `FIELD` | Khai báo field, bao gồm enum constant | `@Flag private int id;` |
| `METHOD` | Khai báo method, gồm element của annotation interface | `@Flag void save() {}` |
| `CONSTRUCTOR` | Khai báo constructor | `@Flag Order() {}` |
| `PARAMETER` | Khai báo formal/exception parameter | `void f(@Flag String name)` |
| `LOCAL_VARIABLE` | Khai báo biến cục bộ, gồm các declaration context được đặc tả hỗ trợ | `@Flag int count = 1;` |
| `TYPE_PARAMETER` | Khai báo tham số kiểu generic | `class Box<@Flag T> {}` |
| `TYPE_USE` | Các type context; còn cho phép một số vị trí khai báo kiểu/tham số kiểu | `class X extends @Flag Base {}` |
| `RECORD_COMPONENT` | Khai báo thành phần record | `record R(@Flag int id) {}` |
| `PACKAGE` | Khai báo package | Trong `package-info.java` |
| `MODULE` | Khai báo module | Trong `module-info.java` |

Các ví dụ trong bảng chỉ có ý nghĩa khi `@Flag` được khai báo với `@Target` phù hợp. Ví dụ `@Target(TYPE)` **không đồng nghĩa** với `@Target(TYPE_USE)`: một kiểu được **khai báo** khác với một kiểu được **dùng** trong biểu thức hoặc type argument.

Về cú pháp, `@Target` nhận một mảng `ElementType[]`. Vì thế `@Target(ElementType.METHOD)` là cách viết ngắn cho mảng một phần tử; nhiều phần tử viết `@Target({ElementType.METHOD, ElementType.FIELD})`.

## 2. Không khai báo @Target: mặc định rộng trong declaration context

Ví dụ:

~~~java
@interface Free {
    String value() default "free";
}

@Free("class")
class Service {
    @Free("field")
    int retries;

    @Free("constructor")
    Service() {}

    @Free("method")
    void execute(@Free("parameter") String input) {
        @Free("local") int x = 1;
    }
}
~~~

Tất cả cách đặt trong đoạn trên đều hợp lệ: `Free` không bị hạn chế bởi một danh sách `@Target` cụ thể. Quy tắc của Java SE 17+ trong **JLS §9.6.4.1** là: một annotation interface không có `@Target` áp dụng được ở **tất cả declaration contexts** và **không có type contexts**.

Điều này có các hệ quả dễ nhầm:

- Có thể gắn `@Free` lên class, field, method, constructor, parameter hoặc local-variable declaration.
- Trong các phiên bản đặc tả hiện đại, **generic type parameter declaration** cũng thuộc nhóm được phép, ví dụ `class Box<@Free T> {}`.
- **Không được mặc định** rằng `@Free` áp dụng được ở type-use-only context, chẳng hạn `class Child extends @Free Parent {}`. Thiếu `@Target` không tương đương với `@Target(ElementType.TYPE_USE)`.
- Java không diễn giải việc thiếu `@Target` là “không cho phép đặt ở đâu”. Ý nghĩa **cấm đặt trực tiếp** thuộc về `@Target({})`.

### Lưu ý tương thích trình biên dịch cho type parameter

Dù quy tắc hiện đại cho phép `class Box<@Free T> {}`, một số **javac trước JDK 21** có lỗi triển khai khiến annotation không có `@Target` bị từ chối ở vị trí type parameter. Lỗi đó đã được sửa trong **JDK 21** (JDK-8303784), kể cả khi biên dịch với `--release 14` trở lên. Vì vậy, nếu bạn đang dùng JDK 17 và thấy trường hợp này báo lỗi, cần đối chiếu **phiên bản javac thực tế** và đặc tả; đừng từ đó kết luận rằng mọi vị trí type parameter đều bị cấm theo JLS.

Một ví dụ độc lập để thử trên JDK 21:

~~~java
@interface FlexibleTypeParameter {}

class Box<@FlexibleTypeParameter T> {}
~~~

Hai dòng này là ví dụ **kiểm tra compile time**, không phải chương trình có `main`. Với JDK 21, có thể dùng `javac --release 17 Box.java` nếu lưu đúng tên file `Box.java`. Không gán ý nghĩa runtime cho annotation chỉ vì compiler chấp nhận vị trí của nó.

## 3. @Target({}): cố ý không cho gắn annotation trực tiếp

Cú pháp này đặt một **mảng ElementType rỗng**:

~~~java
import java.lang.annotation.Target;

@Target({})
@interface Attribute {
    String key();
    String value();
}
~~~

Ý nghĩa: `Attribute` không áp dụng được trực tiếp vào class, method, field, parameter hay bất kỳ type use nào. Nhưng nó vẫn có thể là **giá trị annotation lồng** vì chỗ đó là cú pháp *annotation element value*, không phải đang gắn `@Attribute` làm modifier cho một declaration/type context.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({})
@interface Attribute {
    String key();
    String value();
}

@Target(ElementType.TYPE)
@interface Attributes {
    Attribute[] value();
}

@Attributes({
    @Attribute(key = "owner", value = "platform"),
    @Attribute(key = "tier", value = "internal")
})
class Component {}
~~~

Đoạn này **hợp lệ**: các `@Attribute(...)` là hai giá trị nằm trong element `value` của `@Attributes`. Annotation được gắn trực tiếp lên class là `@Attributes`, nó có target `TYPE`.

Nếu viết:

~~~java
// CỐ Ý SAI: không biên dịch.
//
// @Attribute(key = "owner", value = "platform")
// class Component {}
~~~

thì compiler phải từ chối bởi `Attribute` được khai báo `@Target({})`. Cách thiết kế này thích hợp khi annotation nhỏ chỉ mang metadata có cấu trúc và cần bắt buộc được đặt **bên trong** annotation chính.

### Những điều @Target({}) không có nghĩa

- Nó **không** làm annotation type “vô hiệu” hay “không được khai báo”. Bạn vẫn có thể định nghĩa `@interface Attribute` bình thường.
- Nó **không** biến annotation thành một class để gọi constructor bằng `new`.
- Nó **không** cấm một annotation instance xuất hiện dưới dạng *nested annotation element value*.
- Nó **không** tương đương với `@Target(ElementType.ANNOTATION_TYPE)`. Giá trị `ANNOTATION_TYPE` cho phép gắn annotation **lên khai báo của annotation interface khác**, không chỉ dùng làm giá trị lồng.

## 4. Khai báo @Target cụ thể: compiler kiểm tra vị trí

Đây là cách thông thường khi viết API annotation rõ ràng:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface Timed {}

class Task {
    @Timed
    void run() {}

    // @Timed int timeout; // CỐ Ý SAI: field không phải method.
}
~~~

Nếu bỏ dấu comment ở dòng field, `javac` sẽ báo lỗi vị trí không hợp lệ, thường có thông điệp như `annotation type not applicable to this kind of declaration`. Thông điệp cụ thể thay đổi tùy compiler/version; **bản chất lỗi** là `Timed` chỉ có target `METHOD` nhưng lại được đặt trong `FIELD` declaration context.

Nếu muốn cho phép cả method lẫn field, khai báo nhiều target:

~~~java
@Target({ElementType.METHOD, ElementType.FIELD})
@interface Audited {}
~~~

Một `ElementType` không được lặp lại trong cùng danh sách `@Target`:

~~~java
// CỐ Ý SAI: cùng FIELD xuất hiện hai lần.
//
// @Target({ElementType.FIELD, ElementType.FIELD})
// @interface DuplicateTarget {}
~~~

Việc lặp hằng enum ở đây là **compile-time error**, không phải chỉ là redundancy mà compiler bỏ qua.

### @Target áp dụng lên annotation interface, không phải annotation sử dụng nó

`@Target` bản thân cũng là một annotation với `@Target(ANNOTATION_TYPE)`. Vì thế hãy đặt nó trên **khai báo `@interface`**, không gắn tùy tiện lên class nghiệp vụ:

~~~java
@Target(ElementType.METHOD)
@interface Endpoint {}

// @Target(ElementType.METHOD) // CỐ Ý SAI: @Target không dành cho class.
// class OrderService {}
~~~

Sau khi định nghĩa `Endpoint`, dùng `@Endpoint` ở nơi cho phép. `@Target` là **quy tắc thiết kế annotation type**, không phải một annotation để tùy biến từng lần dùng `@Endpoint`.

## 5. Ví dụ Java 17 chạy được: ba trường hợp trong cùng chương trình

Lưu toàn bộ chương trình sau trong **TargetDemo.java** (một file; các annotation và class phụ đều không phải `public`):

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@interface Flexible {
    String value() default "marker";
}

@Target({})
@Retention(RetentionPolicy.RUNTIME)
@interface Detail {
    String text();
}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface Description {
    Detail detail();
}

@Target({ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@interface Audited {}

@Flexible("class")
@Description(detail = @Detail(text = "nested"))
final class Handler {
    @Flexible("field")
    @Audited
    int count = 2;

    @Flexible("constructor")
    Handler() {}

    @Flexible("method")
    @Audited
    void run(@Flexible("parameter") String input) {
        @Flexible("local") int local = count;
        System.out.println(input + ":" + local);
    }
}

public class TargetDemo {
    public static void main(String[] args) throws Exception {
        Class<Handler> type = Handler.class;
        System.out.println("class=" + type.getAnnotation(Flexible.class).value());
        System.out.println("detail=" + type.getAnnotation(Description.class).detail().text());
        System.out.println("field=" + type.getDeclaredField("count")
                .getAnnotation(Flexible.class).value());
        System.out.println("method=" + type.getDeclaredMethod("run", String.class)
                .isAnnotationPresent(Audited.class));
        new Handler().run("ok");
    }
}
~~~

Tại thư mục chứa file, chạy:

~~~bash
javac --release 17 -encoding UTF-8 TargetDemo.java
java TargetDemo
~~~

**Stdout chính xác:**

~~~text
class=class
detail=nested
field=field
method=true
ok:2
~~~

Giải thích kết quả:

1. **`Flexible` không có `@Target`**: được gắn lên khai báo class, field, constructor, method, parameter, local variable trong ví dụ. Chương trình đọc được các annotation trên class/field bởi ta **đặt thêm `@Retention(RUNTIME)`**. Chú ý: annotation gắn vào *declaration* của local variable không được reflection hiển thị như annotation trên class/field, kể cả khi retention là RUNTIME.
2. **`Detail` có `@Target({})`**: không thể gắn trực tiếp lên `Handler`, nhưng cú pháp `@Description(detail = @Detail(text = "nested"))` hợp lệ. `Description` là annotation áp dụng lên class.
3. **`Audited` chỉ có `FIELD` và `METHOD`**: được gắn lên `count` và `run`; nếu gắn nó lên constructor hoặc parameter, compiler sẽ từ chối.
4. Output `method=true` phản ánh việc annotation `Audited` được đọc qua reflection trên method sau khi dùng `RUNTIME` retention. **`@Target` tự nó không khiến annotation có mặt ở runtime**.

Đây là một ví dụ dạy cú pháp và phản chiếu metadata. Nó chưa triển khai cơ chế business audit. Muốn tự động audit khi gọi method, framework hoặc mã của ứng dụng vẫn phải **đọc và xử lý annotation** tương ứng.

## 6. Những lỗi đặt sai vị trí: tình huống và cách sửa

Các đoạn trong bảng là minh họa để xét quy tắc; những dòng được ghi **lỗi** sẽ không biên dịch nếu chèn trực tiếp vào chương trình.

| Khai báo annotation | Nơi sử dụng | Kết quả và cách xử lý |
| --- | --- | --- |
| Không có `@Target` | `@Flexible class C {}` | Hợp lệ: declaration context `TYPE` |
| Không có `@Target` | `class C extends @Flexible Base {}` | Sai: đây là type context, cần `TYPE_USE` |
| `@Target({})` | `@Detail class C {}` | Sai: tập target rỗng |
| `@Target({})` | `@Wrapper(value = @Detail(...))` | Hợp lệ: nested annotation value, nếu `Wrapper` khai báo element phù hợp |
| `@Target(METHOD)` | `@Timed void run() {}` | Hợp lệ: method declaration |
| `@Target(METHOD)` | `@Timed int count;` | Sai: field declaration; thêm `FIELD` nếu API thực sự cần |
| `@Target(FIELD)` | `void run(@Tag String s) {}` | Sai: formal parameter declaration; thêm `PARAMETER` nếu thích hợp |
| `@Target(TYPE)` | `@Flag class C {}` | Hợp lệ: class declaration |
| `@Target(TYPE)` | `List<@Flag String> items;` | Sai: type argument; cần `TYPE_USE` |
| `@Target(ANNOTATION_TYPE)` | `@Meta @interface A {}` | Hợp lệ: khai báo annotation interface |
| `@Target({METHOD, FIELD})` | Gắn lên method hoặc field | Hợp lệ ở hai declaration contexts đã nêu |

Ở các hàng dùng tên ngắn `METHOD`, `FIELD`, `TYPE`, giả định đã import tĩnh enum constants hoặc đặt đầy đủ tiền tố `ElementType.` trong mã chạy thật.

### 6.1. Lỗi dễ nhầm giữa khai báo field và type use

Nhìn đoạn:

~~~java
@Flexible
String name;
~~~

Có thể tưởng `@Flexible` đang gắn vào kiểu `String`. Nhưng ở đây nó có thể được hiểu là **declaration annotation của field `name`**, nên vẫn hợp lệ khi `Flexible` thiếu `@Target`.

Muốn kiểm tra annotation hỗ trợ **TYPE_USE** hay không, hãy dùng vị trí không thể bị nhầm với field declaration:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface NonNullLike {}

class TypeUseExample {
    List<@NonNullLike String> names;
}
~~~

Đoạn này **biên dịch hợp lệ** bởi `@NonNullLike` cho phép dùng trên thành phần kiểu generic argument. Tuy nhiên, tên `NonNullLike` chỉ là metadata; compiler Java chuẩn **không tự kiểm tra non-null** chỉ vì ta tự khai báo annotation đó. Để thực thi quy tắc nullability cần checker/processor thích hợp.

### 6.2. TYPE_USE còn có thể áp dụng ở một số declaration contexts

Theo `ElementType` API, `TYPE_USE` cũng được phép xuất hiện trên **khai báo class/interface và type parameter** (ngoài type contexts thông thường). Điều này phục vụ công cụ phân tích kiểu.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface CheckedType {}

@CheckedType
class Container<@CheckedType T> {}
~~~

Cả hai vị trí trên hợp lệ theo quy tắc `TYPE_USE`. Vì thế không nên kết luận đơn giản rằng `TYPE_USE` “chỉ dành cho `new` hoặc cast”.

Ngược lại, `@Target(TYPE)` **không cấp quyền** gắn annotation vào mọi lần một kiểu xuất hiện. Nó chủ yếu nhắm tới khai báo class/interface/enum/record.

### 6.3. Vị trí package và module

Nếu annotation có `@Target(PACKAGE)` hoặc không khai báo `@Target`, vị trí dành cho package annotation là **package declaration trong `package-info.java`**, chẳng hạn:

~~~java
// Tệp package-info.java (đoạn minh họa, không thuộc TargetDemo.java)
@com.example.annotations.PackageLabel
package com.example.orders;
~~~

Ví dụ trên giả định đã tồn tại annotation `com.example.annotations.PackageLabel` có target hợp lệ. Tương tự, module annotations phải được đặt trên module declaration trong `module-info.java`. Việc class annotation hợp lệ trên class **không có nghĩa** bạn có thể viết tùy ý một package annotation ngay giữa source file.

## 7. @Target, @Retention và @Inherited là ba câu hỏi riêng

Giả sử:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface Logged {}
~~~

- **`@Target(METHOD)`**: ở đâu được phép gắn? Trên method declaration.
- **`@Retention(RUNTIME)`**: runtime reflection có khả năng đọc annotation từ method không? Có (nếu được dùng hợp lệ và truy vấn đúng method).
- **`@Inherited`** (nếu thêm và nếu target cho phép) nói về quy tắc *kế thừa class annotation* khi truy vấn trên subclass; nó không phải cách tự động kế thừa annotation method và cũng không mở rộng `@Target`. Với annotation chỉ dành cho method như `Logged`, `@Inherited` không làm nó xuất hiện ở overridden methods.

Nếu **không khai báo `@Retention`**, mặc định là `RetentionPolicy.CLASS`; annotation có thể tồn tại trong class file nhưng không được runtime reflection xem như annotation có RUNTIME retention. Vì vậy, “biên dịch cho phép đặt” và “runtime đọc thấy” là hai bước cần kiểm tra độc lập.

Bản thân **annotation không tự chạy logic**: compiler đảm bảo tính hợp lệ của vị trí; application/framework phải định nghĩa ý nghĩa nghiệp vụ, ví dụ quét method có `@Logged` và tạo logging interceptor.

## 8. Chọn target để thiết kế annotation hữu ích

Khi thiết kế annotation mới, nên bắt đầu từ **consumer và nơi gắn dự kiến**:

1. Nếu annotation mô tả hành vi của **method** (ví dụ metric, transaction boundary), khai báo `@Target(METHOD)`.
2. Nếu annotation mô tả **field**, cân nhắc `@Target(FIELD)`; nếu dùng cả field và parameter, khai báo hai target rõ ràng.
3. Nếu annotation mô tả **kiểu dữ liệu sử dụng** (type argument, cast, generic type-use), chọn `TYPE_USE` và chuẩn bị công cụ phân tích cần thiết.
4. Nếu annotation chỉ là phần tử cấu trúc **lồng trong annotation khác**, chọn `@Target({})`; đừng cho phép dùng trực tiếp khi điều đó không có ý nghĩa.
5. Nếu thực sự muốn annotation áp dụng rộng cho mọi **declaration context**, có thể bỏ `@Target`, nhưng hãy hiểu rằng điều đó không mặc nhiên bao gồm type contexts.

Quy tắc **fail fast khi biên dịch** rất hữu ích: `@Target` cụ thể giúp người dùng API phát hiện việc đặt metadata nhầm chỗ trước khi chạy application. Giới hạn đủ chính xác cũng giúp tool, IDE và annotation processor biết vị trí nào cần quan tâm.

Cần cân nhắc tác động tương thích API khi sửa target: việc **thu hẹp** tập target có thể khiến các source sử dụng hợp lệ trước đây không còn biên dịch; mở rộng target có thể tạo thêm cách dùng mà framework/processor chưa hỗ trợ. Khi phát hành thư viện, hãy ghi rõ target và kiểm thử các call sites thực tế.

## 9. Những lỗi hiểu nhầm thường gặp

**Nhầm 1: Không có @Target tức không được dùng annotation ở đâu.** Sai: trong Java hiện đại, nó được áp dụng tại mọi declaration context. Muốn không cho gắn trực tiếp phải dùng `@Target({})`.

**Nhầm 2: @Target({}) vô dụng.** Sai: đó là cách rõ ràng để định nghĩa annotation chỉ làm nested annotation value trong một annotation khác, chẳng hạn `@Detail` chứa thuộc tính của `@Description`.

**Nhầm 3: Không có @Target tương đương @Target(TYPE_USE).** Sai: việc thiếu `@Target` không mở type contexts. Phân biệt `@Flag String field;` (có thể là declaration annotation) với `List<@Flag String>` (type-use context rõ ràng).

**Nhầm 4: @Target(TYPE) có nghĩa annotation được viết trên bất kỳ tên type nào.** Sai: `TYPE` nói về khai báo kiểu; `TYPE_USE` nói về dùng kiểu ở các vị trí được JLS xác định.

**Nhầm 5: @Target({METHOD, FIELD}) khiến Java tự log/audit method và field.** Sai: `@Target` chỉ là ràng buộc vị trí. Runtime behavior cần consumer.

**Nhầm 6: @Retention(RUNTIME) sẽ giúp vượt qua lỗi sai vị trí.** Sai: compiler vẫn từ chối annotation dùng sai `@Target` dù retention là RUNTIME.

**Nhầm 7: Thêm @Target cùng ElementType lặp lại không sao.** Sai: cùng một `ElementType` xuất hiện hai lần trong giá trị `@Target` là compile-time error.

**Nhầm 8: Những dòng không có lỗi trên JDK mới chắc chắn compile trên mọi javac cũ.** Không hẳn: đối với annotation không có `@Target` trên type parameter, javac trước JDK 21 có lỗi tương thích đã được sửa. Cần biết cả đặc tả nguồn và công cụ biên dịch đang sử dụng.

## 10. Bài tập tự kiểm tra

Xem bốn khai báo:

~~~java
@interface A {}

@java.lang.annotation.Target({})
@interface B {}

@java.lang.annotation.Target(java.lang.annotation.ElementType.METHOD)
@interface C {}

@java.lang.annotation.Target(java.lang.annotation.ElementType.TYPE_USE)
@interface D {}
~~~

Hãy tự dự đoán các trường hợp sau (không thêm `@Retention`):

1. Gắn `@A` lên class: **hợp lệ**, vì không khai báo `@Target` và class là declaration context.
2. Gắn `@A` vào generic type argument, ví dụ `List<@A String>`: **không hợp lệ**, vì là type context.
3. Gắn `@B` trực tiếp lên một field: **không hợp lệ**, vì tập target rỗng.
4. Dùng `@B` làm giá trị cho element có kiểu `B` trong annotation khác: **hợp lệ**, vì đó là nested annotation element value.
5. Gắn `@C` lên method: **hợp lệ**; gắn lên constructor: **không hợp lệ**.
6. Gắn `@D` lên kiểu trong `List<@D String>`: **hợp lệ**, vì là TYPE_USE.
7. Khi compile thành công, dùng reflection tìm `@A` trên class: theo mặc định **không hiện ra**, vì thiếu `@Retention` nên retention mặc định là CLASS; đó là chuyện khác với `@Target`.

### Cách tự kiểm tra lỗi có chủ ý

Đặt mỗi trường hợp **sai** vào một file Java riêng có khai báo annotation tương ứng rồi chạy:

~~~bash
javac --release 17 -encoding UTF-8 Example.java
~~~

Dự kiến compiler trả **lỗi biên dịch** với các vị trí không phù hợp; thông báo tùy phiên bản `javac`. Những đoạn được chú thích “cố ý sai” trong bài này nhằm minh họa compile error và **không được ghép vào file runnable TargetDemo.java**.

## 11. Tài liệu đối chiếu

- Java SE 21 API: **`java.lang.annotation.Target`** — https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Target.html
- Java SE 21 API: **`java.lang.annotation.ElementType`** — https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/ElementType.html
- Java Language Specification, Java SE 21: **§9.6.4.1 @Target** — https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.1
- Java Language Specification, Java SE 21: **§9.7.4 Where Annotations May Appear** — https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4
- JDK 21 release notes, bug **JDK-8303784** — https://www.oracle.com/java/technologies/javase/21-relnote-issues.html

Khi thấy một annotation bị báo “đặt sai vị trí”, hãy xác định annotation interface **có `@Target` hay không**, nếu có thì **tập `ElementType` là gì**, và chỗ viết annotation là **declaration hay type context**. Đặc biệt, “không khai báo `@Target`” và “`@Target({})`” có tác dụng gần như đối nghịch: trường hợp thứ nhất rộng trên declarations, trường hợp thứ hai cố ý không cho dùng trực tiếp.