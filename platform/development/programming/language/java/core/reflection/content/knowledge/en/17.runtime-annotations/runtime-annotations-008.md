# getAnnotationsByType khác getDeclaredAnnotationsByType trong Java Reflection

## 1. Vấn đề: tìm annotation theo loại không chỉ là đọc danh sách annotation

Khi sử dụng Java Reflection, một lớp, phương thức hoặc field có thể mang **runtime annotation**. Nếu annotation được khai báo lặp lại nhờ `@Repeatable`, một phần tử có thể có nhiều annotation cùng loại. Nếu annotation được đánh dấu `@Inherited`, một **class** có thể quan sát annotation từ superclass khi không khai báo annotation cùng loại ở chính mình.

Hai API trong `java.lang.reflect.AnnotatedElement` giải quyết hai phạm vi khác nhau:

- `getAnnotationsByType(Class<T> annotationClass)`: tìm tất cả annotation **associated** của một loại tại phần tử. Với `Class`, kết quả có thể bao gồm annotation kế thừa từ superclass theo luật `@Inherited`.
- `getDeclaredAnnotationsByType(Class<T> annotationClass)`: tìm tất cả annotation của loại đó **directly present** hoặc **indirectly present** tại **chính phần tử được truy vấn**, không lấy từ superclass.

Điểm dễ nhầm là cả hai đều hỗ trợ **repeatable annotation** bằng cách mở rộng (*unpack*) container annotation. Khác biệt quan trọng của chúng là **ngữ nghĩa kế thừa**, chứ không phải “một phương thức hiểu repeatable, phương thức kia không”.

> Trong bài, “declared” nghĩa là metadata nằm trên phần tử hiện tại; nó **không** nghĩa là annotation có visibility `private`, và cũng không tương đương với `getDeclaredAnnotations()` vì phương thức không có `ByType` thường không tự mở rộng container.

## 2. Bốn khái niệm: trực tiếp, gián tiếp, present, associated

Để hiểu chính xác hai API, cần phân biệt các trạng thái annotation:

| Thuật ngữ | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| **Directly present** | Annotation của đúng loại xuất hiện trực tiếp trong metadata runtime của phần tử | `@Label("x")` khai báo một lần |
| **Indirectly present** | Annotation được chứa trong **containing annotation** của một loại `@Repeatable` | Hai `@Label` được compiler đóng vào `@Labels` |
| **Present** | Directly present hoặc annotation kế thừa theo quy tắc `@Inherited` áp dụng cho `Class` | `Child` kế thừa một annotation hiện diện trên `Parent` |
| **Associated** | Directly present, indirectly present, hoặc được kế thừa theo quy tắc áp dụng nếu trên phần tử hiện tại không có annotation của loại đó theo cách trực tiếp/gián tiếp | `Child.class.getAnnotationsByType(Label.class)` có thể trả các `Label` ở `Parent` |

Cụ thể:

- `getDeclaredAnnotationsByType(T.class)` trả các annotation loại `T` **trực tiếp và gián tiếp** trên phần tử đang xét.
- `getAnnotationsByType(T.class)` trả các annotation loại `T` **associated** với phần tử; nếu phần tử là `Class` và `T` có `@Inherited`, phương thức có thể xét superclass.
- Nếu class con **đã có** annotation loại `T` trực tiếp hoặc gián tiếp, kết quả của `getAnnotationsByType` ưu tiên tập **cục bộ** này, **không tự gộp** với tập cùng loại ở superclass.
- `@Inherited` không làm annotation trên **method, field hoặc interface** tự được kế thừa theo cùng cách như annotation trên class.

### Repeatable annotation và container

Với kiểu annotation lặp lại:

```java
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
}
```

Đây là phần minh họa cú pháp, chưa có `@Retention(RUNTIME)` nên **chưa đủ** để đọc qua Reflection ở runtime. Phần ví dụ runnable bên dưới bổ sung đầy đủ metadata.

Hai annotation:

```java
@Label("alpha")
@Label("beta")
class Service {}
```

thường được thể hiện trong class file bằng **container** `@Labels` với mảng `value()` chứa hai `@Label`. Do đó:

- `Service.class.getDeclaredAnnotationsByType(Label.class)` thấy hai `Label`.
- `Service.class.getDeclaredAnnotation(Label.class)` thường trả `null` vì runtime metadata lưu **container `Labels`**, không lưu hai `Label` như hai annotation trực tiếp độc lập.
- `Service.class.getDeclaredAnnotation(Labels.class)` thấy container `Labels`.
- `Service.class.getDeclaredAnnotations()` có thể cho biết container `Labels`, không tự bung ra thành hai `Label`.

Đây là lý do cần sử dụng API có hậu tố **`ByType`** khi muốn lấy danh sách các annotation repeatable theo **loại annotation bên trong**, thay vì tự dò và unpack container.

## 3. So sánh nhanh các API Reflection

| API | Loại trả về | Mở rộng annotation repeatable? | Xét kế thừa? |
| --- | --- | --- | --- |
| `getAnnotation(T.class)` | `T` hoặc `null` | Không phải API chuyên để unpack tất cả phần tử trong container | Có thể, theo `@Inherited` và luật present trên `Class` |
| `getDeclaredAnnotation(T.class)` | `T` hoặc `null` | Không tự trả nhiều annotation được chứa trong container | Không |
| `getAnnotationsByType(T.class)` | `T[]` | **Có** | **Có thể**, với `Class` và `@Inherited` |
| `getDeclaredAnnotationsByType(T.class)` | `T[]` | **Có** | **Không** |
| `getAnnotations()` | `Annotation[]` | Không tự chuyển container thành nhiều `T` | Có thể phản ánh annotation kế thừa theo quy tắc runtime |
| `getDeclaredAnnotations()` | `Annotation[]` | Không tự chuyển container thành nhiều `T` | Không |

**Dấu hiệu lựa chọn:** khi đọc một repeatable annotation từ class và muốn xem annotation hiệu lực sau kế thừa, dùng `getAnnotationsByType`. Khi viết công cụ phân tích **đúng annotation đặt trên class hiện tại**, dùng `getDeclaredAnnotationsByType`.

Các API có `Declared` không đồng nghĩa “chỉ trả annotation thuộc class chưa biên dịch”; `Class`, `Method`, `Field` và các đối tượng `AnnotatedElement` khác đều có thể cung cấp các phương thức này theo phạm vi tương ứng.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu nguyên chương trình sau vào **`AnnotationByTypeDemo.java`**. Chương trình có annotation `Label` vừa `@Repeatable` vừa `@Inherited`, và container `Labels` cũng có retention runtime/`@Inherited`. Các class kiểm thử gồm:

- `Parent`: hai nhãn lặp lại.
- `Child`: không khai báo `Label` riêng, nên có thể thấy nhãn từ superclass khi dùng API associated.
- `OwnChild`: một nhãn riêng, che tập nhãn inherited của `Parent` đối với truy vấn by-type.
- `TwoChild`: hai nhãn riêng, kiểm tra container local.
- `ContainerChild`: khai báo trực tiếp container `@Labels`.
- `Implementation`: triển khai interface đã đánh dấu, chứng minh `@Inherited` không chạy qua interface.

```java
import java.lang.annotation.*;
import java.util.*;
import java.util.stream.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface Labels {
    Label[] value();
}

@Label("parent-a")
@Label("parent-b")
class Parent {}

class Child extends Parent {}

@Label("child")
class OwnChild extends Parent {}

@Label("local-a")
@Label("local-b")
class TwoChild extends Parent {}

@Labels({@Label("explicit-a"), @Label("explicit-b")})
class ContainerChild extends Parent {}

@Label("interface-only")
interface Contract {}

class Implementation implements Contract {}

public class AnnotationByTypeDemo {
    private static String names(Label[] labels) {
        return Arrays.stream(labels)
                .map(Label::value)
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
    }

    private static void describe(Class<?> type) {
        System.out.println(type.getSimpleName()
                + ": all=" + names(type.getAnnotationsByType(Label.class))
                + " declared="
                + names(type.getDeclaredAnnotationsByType(Label.class)));
    }

    public static void main(String[] args) {
        describe(Parent.class);
        describe(Child.class);
        describe(OwnChild.class);
        describe(TwoChild.class);
        describe(ContainerChild.class);
        describe(Implementation.class);

        System.out.println("parent direct single: "
                + (Parent.class.getDeclaredAnnotation(Label.class) != null));
        System.out.println("parent declared container: "
                + (Parent.class.getDeclaredAnnotation(Labels.class) != null));
        System.out.println("child inherited container: "
                + (Child.class.getAnnotation(Labels.class) != null));
        System.out.println("child declared container: "
                + (Child.class.getDeclaredAnnotation(Labels.class) != null));
    }
}
```

Biên dịch bằng **Java 17** hoặc JDK mới hơn:

```bash
javac --release 17 AnnotationByTypeDemo.java
java AnnotationByTypeDemo
```

**Output chính xác** khi chạy chương trình độc lập:

```text
Parent: all=[parent-a, parent-b] declared=[parent-a, parent-b]
Child: all=[parent-a, parent-b] declared=[]
OwnChild: all=[child] declared=[child]
TwoChild: all=[local-a, local-b] declared=[local-a, local-b]
ContainerChild: all=[explicit-a, explicit-b] declared=[explicit-a, explicit-b]
Implementation: all=[] declared=[]
parent direct single: false
parent declared container: true
child inherited container: true
child declared container: false
```

Hàm `names` sắp xếp nhãn theo tên để output ổn định và dễ đọc, không phụ thuộc vào cách trình bày thứ tự của các annotation trong ví dụ. Khi cần bảo toàn thứ tự xuất hiện của các annotation repeatable, không được tùy tiện sắp xếp kết quả như hàm trình diễn này.

### 4.1. Parent: hai API đều trả hai annotation

`Parent` tự khai báo hai `@Label`. Trong metadata runtime, compiler dùng container `@Labels` cho tập lặp lại. Hai API `getAnnotationsByType(Label.class)` và `getDeclaredAnnotationsByType(Label.class)` đều unpack container thành hai `Label`. Bởi vậy cả `all` và `declared` đều là `[parent-a, parent-b]`.

### 4.2. Child: chỉ API không có Declared mới kế thừa

`Child extends Parent` nhưng không khai báo `@Label`. Do `Label` có `@Inherited`, lời gọi:

```java
Child.class.getAnnotationsByType(Label.class)
```

trả các nhãn associated từ superclass: `[parent-a, parent-b]`.

Trong khi đó:

```java
Child.class.getDeclaredAnnotationsByType(Label.class)
```

trả **mảng rỗng**, vì `Child` không khai báo `Label` trực tiếp hay gián tiếp. Hai API khác nhau về **phạm vi**, không khác nhau về khả năng unpack container.

### 4.3. OwnChild: annotation cục bộ không hợp nhất với superclass

`OwnChild` có `@Label("child")` trực tiếp. Vì đã có `Label` cục bộ, `getAnnotationsByType(Label.class)` trả `[child]`, **không** trả `[parent-a, parent-b, child]`. Phương thức declared cũng trả `[child]`.

Đây là khác biệt thực tế với một số kỳ vọng “annotation từ các tầng được gộp tất cả”. Đối với **một loại repeatable annotation**, quy tắc `@Inherited` của truy vấn associated không tự thêm annotation của superclass khi class hiện tại đã có annotation loại đó.

Nếu nghiệp vụ thật sự muốn tập annotation **gộp từ mọi lớp trong hierarchy**, cần tự duyệt `getSuperclass()` và áp dụng chính sách gộp, xung đột, thứ tự theo yêu cầu ứng dụng.

### 4.4. TwoChild: có nhiều annotation cục bộ

`TwoChild` khai báo hai `@Label`. Cả hai API trả đúng hai annotation cục bộ; các nhãn ở `Parent` không được thêm. `getDeclaredAnnotationsByType` trả được cả hai dù class file chứa container chứ không nhất thiết chứa hai annotation `Label` tách rời.

### 4.5. ContainerChild: khai báo container cũng được unpack

`ContainerChild` viết trực tiếp:

```java
@Labels({@Label("explicit-a"), @Label("explicit-b")})
```

Mỗi `Label` bên trong được xem là *indirectly present* theo luật repeatable. Hai API by-type đều trả `[explicit-a, explicit-b]`. Vì vậy **không nhất thiết** người viết source phải dùng cú pháp `@Label` lặp lại; container hợp lệ cũng được nhận diện.

### 4.6. Implementation: @Inherited không chạy qua interface

`Contract` là một interface có `@Label("interface-only")`. `Implementation implements Contract` **không** kế thừa annotation qua interface trong luật `@Inherited`. Vì vậy cả hai truy vấn của `Implementation.class` trả mảng rỗng.

`@Inherited` chỉ có hiệu lực khi tìm annotation trên **class**, đi theo quan hệ superclass thích hợp; không biến interface annotation thành annotation mặc định cho mọi class triển khai.

### 4.7. Vì sao getDeclaredAnnotation(Label.class) ở Parent trả null?

Hai `@Label` trên `Parent` đã được biểu diễn bằng containing annotation `@Labels`. Do đó `Parent.class.getDeclaredAnnotation(Label.class)` không nhìn thấy một annotation `Label` **directly present** đơn lẻ và trả `null`. Nhưng `getDeclaredAnnotation(Labels.class)` trả container thật, nên in `true`.

`Child.class.getAnnotation(Labels.class)` là `true` bởi container `Labels` cũng có `@Inherited`, trong khi `getDeclaredAnnotation(Labels.class)` ở Child là `null`. Cùng một hiện tượng nhưng đối với **loại annotation container**.

**Cảnh báo:** Nếu chỉ gọi `getAnnotation(Label.class)` khi annotation repeatable xuất hiện hai lần, bạn có thể tưởng rằng annotation không tồn tại. Hãy dùng `getAnnotationsByType(Label.class)` nếu muốn lấy toàn bộ instance của loại repeatable.

## 5. Kiểm tra retention trước khi so sánh hai API

Cả `Label` và `Labels` trong chương trình đều có `@Retention(RUNTIME)` để runtime Reflection nhìn thấy repeatable annotation. Nếu annotation không có retention runtime phù hợp, cả hai phương thức `ByType` có thể trả mảng rỗng; đó là lỗi về metadata visibility, không chứng tỏ một API xử lý container khác API còn lại. Các quy tắc khai báo container thuộc bài repeatable trước.

## 6. Phạm vi kế thừa trong hai API `ByType`

`getAnnotationsByType(T.class)` có thể tìm tới superclass **khi phần tử là class**, annotation type `T` có `@Inherited`, và class hiện tại không có annotation loại `T` trực tiếp/gián tiếp. `getDeclaredAnnotationsByType(T.class)` luôn giới hạn ở phần tử hiện tại.

Điều đó **không** làm annotation từ interface được implements, method được override hoặc field bị hide tự xuất hiện trên phần tử mới. Nếu `getMethod()` trả method gốc khai báo ở superclass, annotation đọc được vẫn thuộc chính `Method` đó. Khi framework muốn gộp từ nhiều lớp/interface hoặc method hierarchy, cần chính sách traversal và giải quyết xung đột riêng.

## 7. Quy tắc chọn API theo mục đích

| Nhu cầu thực tế | API phù hợp | Lý do |
| --- | --- | --- |
| Đọc tất cả `@Label` có hiệu lực trên một class, kể cả inherited theo luật Java | `clazz.getAnnotationsByType(Label.class)` | Kết quả associated, hỗ trợ repeatable và `@Inherited` |
| Chỉ đọc `@Label` viết trên chính class này | `clazz.getDeclaredAnnotationsByType(Label.class)` | Không đi ngược superclass |
| Tìm tất cả annotation của một loại repeatable ở method hiện tại | `method.getDeclaredAnnotationsByType(Label.class)` hoặc `getAnnotationsByType` tùy ngữ nghĩa | Không tự kế thừa annotation từ method override |
| Kiểm tra có một annotation **trực tiếp** kiểu `T` hay không | `getDeclaredAnnotation(T.class)` | Nhưng không đủ khi repeatable được đóng trong container |
| Xem container vật lý của repeatable annotation | `getDeclaredAnnotation(Container.class)` | Kiểm tra container được khai báo |
| Duyệt toàn bộ annotation metadata được declared, kể cả loại khác | `getDeclaredAnnotations()` | Trả danh sách annotation metadata; không thay thế by-type để unpack |
| Muốn gộp annotation của **mọi lớp** trong inheritance chain, dù lớp con đã có | Tự duyệt `getSuperclass()` và `getDeclaredAnnotationsByType` | Quy tắc by-type associated không tự gộp các tầng |
| Muốn lấy annotation từ interface hoặc overridden methods theo chính sách framework | Tự duyệt hierarchy và chọn quy tắc xung đột | `@Inherited` không đáp ứng yêu cầu này |

### Mẫu đọc metadata class cục bộ

```java
static Label[] localLabels(Class<?> clazz) {
    return clazz.getDeclaredAnnotationsByType(Label.class);
}
```

### Mẫu đọc các annotation associated

```java
static Label[] effectiveLabels(Class<?> clazz) {
    return clazz.getAnnotationsByType(Label.class);
}
```

Hai đoạn là method Java minh họa có thể đặt trong một class thích hợp, sử dụng `Label` được khai báo trong ví dụ chính. Hãy đặt tên `localLabels` hoặc `effectiveLabels` có chủ ý; một tên chung như `findLabels` thường khiến người đọc không biết hàm có bao gồm inherited hay không.

## 8. Nếu muốn kết quả gộp từ tất cả superclass thì phải tự duyệt

Nhiều framework muốn **kết hợp** các annotation từ class hiện tại và mọi superclass, ngay cả khi lớp hiện tại có annotation cùng loại. `getAnnotationsByType` **không** đáp ứng đầy đủ quy tắc gộp này.

Ví dụ một tiện ích nhận các instance cục bộ theo thứ tự từ class con lên class cha:

```java
static java.util.List<Label> collectEveryLevel(Class<?> type) {
    java.util.List<Label> result = new java.util.ArrayList<>();

    for (Class<?> current = type;
         current != null;
         current = current.getSuperclass()) {

        Label[] local =
                current.getDeclaredAnnotationsByType(Label.class);
        java.util.Collections.addAll(result, local);
    }
    return result;
}
```

Đây là một **phương thức Java minh họa** sử dụng `Label` đã khai báo. Đặt nó trong một class hoặc tiện ích của ứng dụng. Với `OwnChild.class`, tiện ích này thu được `child`, `parent-a`, `parent-b` theo thứ tự tầng và thứ tự các annotation trả về ở mỗi tầng.

Điểm cần ghi nhớ:

- Đây là **quy tắc ứng dụng tự định nghĩa**, không phải hành vi mặc định của `getAnnotationsByType`.
- Có thể cần loại trùng, cho lớp con ưu tiên, cho phép override hoặc hợp nhất giá trị annotation theo domain.
- Ví dụ trên duyệt superclass, **không** duyệt interface. Muốn interface phải thêm logic riêng, tránh lặp trong đồ thị interface và quyết định thứ tự.
- Không chọn `getAnnotationsByType` ở mỗi tầng nếu định gộp trực tiếp: annotation inherited có thể bị đếm lại ở nhiều tầng. `getDeclaredAnnotationsByType` thích hợp hơn để thu **chỉ metadata mỗi tầng**.

## 9. Phần khác biệt với getDeclaredAnnotations()

Khi có một `@Repeatable(Label)`, nhiều người tìm bằng:

```java
for (Annotation a : clazz.getDeclaredAnnotations()) {
    System.out.println(a.annotationType());
}
```

Nếu repeatable `Label` xuất hiện hai lần, danh sách có thể chứa **`Labels`**, là container, chứ không phải hai object `Label` được phẳng hóa. Mặt khác, `getDeclaredAnnotationsByType(Label.class)` được thiết kế để trả hai `Label`.

Vì thế:

- Nếu muốn **mọi annotation metadata loại bất kỳ**, `getDeclaredAnnotations()` hợp lý.
- Nếu muốn **tất cả instance của một loại repeatable cụ thể**, dùng `getDeclaredAnnotationsByType(T.class)`.
- Nếu muốn **tất cả instance liên quan tới một loại, bao gồm thừa kế phù hợp**, dùng `getAnnotationsByType(T.class)`.

Tương tự, `getAnnotations()` là danh sách các annotation hiện diện theo ngữ nghĩa API đó, **không** phải hàm luôn flatten mọi container repeatable thành các phần tử bên trong. Không dùng `getAnnotations().length` để suy luận chắc chắn số repeatable annotations.

## 10. Một số điểm dễ gây hiểu lầm

### 10.1. Có @Inherited nhưng class con vẫn không thấy annotation

Hãy kiểm tra bốn điều:

1. Annotation thật sự có `@Retention(RUNTIME)` không?
2. Annotation loại chính có `@Inherited` không? Nếu repeatable, container được khai báo nhất quán chưa?
3. Phần tử đang truy vấn có thật là **class subclass** theo quan hệ `extends` không, hay chỉ `implements` một interface?
4. Class con có annotation cùng loại **cục bộ** không? Nếu có, phương thức by-type associated trả tập local, không cộng tập superclass.

### 10.2. Có nhiều @Label nhưng getAnnotation(Label.class) trả null

Đó là tình huống thường gặp khi compiler dùng container `@Labels` cho repeatable annotation. Dùng `getAnnotationsByType(Label.class)` hoặc `getDeclaredAnnotationsByType(Label.class)` mới là cách truy xuất nhiều instance.

### 10.3. Không có Declared nghĩa là luôn đọc hết mọi ancestor?

**Không.** `getAnnotationsByType` hỗ trợ ngữ nghĩa `@Inherited` của class, nhưng khi có tập annotation cùng loại local, không tự gộp các tập ở superclass. Khi không có `@Inherited`, nó cũng không tự “quét toàn bộ hierarchy” để trả mọi annotation.

### 10.4. getDeclaredAnnotationsByType chỉ đọc annotation không lặp?

**Sai.** Nó cũng hỗ trợ repeatable annotation, gồm annotation **indirectly present** bên trong container. “Declared” giới hạn **phần tử**, không giới hạn **số lượng annotations**.

### 10.5. Thêm @Inherited trên class được annotate là đủ?

**Sai.** `@Inherited` là meta-annotation dành cho khai báo loại annotation, không phải modifier tùy ý thêm vào `Child` để kích hoạt kế thừa.

### 10.6. @Inherited có tác dụng lên method override?

**Không.** Kế thừa metadata method theo cách tùy chỉnh là công việc của framework. Java Reflection không tự sao chép annotation từ method ở superclass sang method override.

### 10.7. Phụ thuộc thứ tự mảng trả về?

Với repeatable annotations, thứ tự local có thể mang ý nghĩa theo container/source. Hãy xác định quy tắc thứ tự nếu dùng kết quả cho pipeline. Ví dụ chạy ở phần 4 **sắp xếp** để tạo stdout ổn định, không chứng minh rằng JVM luôn trả mảng theo thứ tự từ điển.

### 10.8. Đã compile có annotation thì Reflection phải thấy?

**Không.** Retention `SOURCE`/`CLASS` không đảm bảo runtime Reflection thấy annotation. Nếu số lượng trả về là zero, kiểm tra `@Retention(RUNTIME)` trước khi kết luận API lỗi.

## 11. Lưu ý khi thiết kế framework

Một framework có thể cần hai hành vi khác nhau:

**Chính sách A — inherited, ưu tiên class gần nhất:** Lấy `getAnnotationsByType(T.class)` từ class cần xử lý. Đây gần với ngữ nghĩa annotation associated được Java định nghĩa; phù hợp khi muốn class con có thể thay thế metadata parent bằng giá trị cục bộ.

**Chính sách B — thu mọi tầng:** Duyệt `getSuperclass()` và lấy `getDeclaredAnnotationsByType(T.class)` trên từng class. Đây là chính sách độc lập của framework; cần quyết định merge, order và override rõ ràng.

Nếu annotation nằm trên method hoặc interface và framework muốn kế thừa theo kiểu riêng (ví dụ đọc route annotation ở interface), nên viết thuật toán traversal chuyên biệt. Đừng hy vọng rằng `@Inherited` hoặc `getAnnotationsByType` sẽ làm điều đó cho mọi phần tử.

Việc “effective annotation” ở một số framework như công cụ dependency injection hoặc web routing có thể có ngữ nghĩa **khác** Java Reflection chuẩn (tìm meta-annotation, composed annotation, alias, multiple levels). Khi cần đúng hành vi framework, dùng API của framework; khi cần đúng luật Java Reflection, dựa trên `AnnotatedElement` và `@Inherited`.

## 12. Tự kiểm tra

**Câu 1.** Trên một class có hai `@Label`, `getDeclaredAnnotationsByType(Label.class)` có trả cả hai không?

**Đáp án:** Có. API mở rộng repeatable container để lấy annotation indirectly present trên chính class.

**Câu 2.** `Child extends Parent` không khai báo `Label`, `Label` có `@Inherited`. Hai API trả gì?

**Đáp án:** `Child.class.getAnnotationsByType(Label.class)` có thể trả các `Label` từ Parent; `Child.class.getDeclaredAnnotationsByType(Label.class)` trả rỗng.

**Câu 3.** Nếu `Child` tự khai báo một `@Label("child")`, `getAnnotationsByType` có trả cả Label ở Parent không?

**Đáp án:** Không tự gộp. Tập local của Child được ưu tiên cho loại annotation đó.

**Câu 4.** Vì sao `getDeclaredAnnotation(Label.class)` trên Parent có hai `@Label` có thể trả null?

**Đáp án:** Compiler biểu diễn các annotation lặp lại bằng containing annotation `Labels`; `getDeclaredAnnotation` không phải API flatten nhiều repeatable annotations.

**Câu 5.** `Implementation implements Contract` có tự nhận `@Label` từ interface `Contract` nhờ `@Inherited` không?

**Đáp án:** Không. `@Inherited` không truyền annotation qua `implements`.

**Câu 6.** Phương thức override có tự kế thừa annotation của method superclass khi gọi `getAnnotationsByType` trên `Method` con không?

**Đáp án:** Không. Quy tắc `@Inherited` của Java Reflection áp dụng cho class, không chuyển annotation của method cha sang method override.

**Câu 7.** Vì sao có annotation trong source nhưng hai API by-type đều trả mảng rỗng?

**Đáp án:** Có thể annotation thiếu `@Retention(RUNTIME)`, truy vấn nhầm phần tử/loại, class con không có annotation cục bộ và annotation không `@Inherited`, hoặc chỉ tồn tại trên interface/method khác.

**Câu 8.** Muốn lấy tất cả `Label` ở cả Child và Parent, ngay cả khi Child đã khai báo riêng, dùng gì?

**Đáp án:** Duyệt hierarchy theo `getSuperclass()` và lấy `getDeclaredAnnotationsByType(Label.class)` ở mỗi tầng, sau đó áp dụng quy tắc kết hợp của ứng dụng.

**Ghi nhớ:** **Cả `getAnnotationsByType` và `getDeclaredAnnotationsByType` đều hiểu repeatable annotation**. API có `Declared` chỉ trả những annotation trực tiếp hoặc gián tiếp **trên chính phần tử**; API không có `Declared` có thể áp dụng **`@Inherited` theo superclass khi truy vấn class**, nhưng **không mặc định hợp nhất** tập annotation local với tập ở mọi superclass. Muốn gộp theo chính sách khác, hãy duyệt hierarchy có chủ đích.
