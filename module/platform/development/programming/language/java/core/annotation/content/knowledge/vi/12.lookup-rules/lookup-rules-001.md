# Annotation trực tiếp, gián tiếp, hiện diện và liên kết trong Java

## 1. Vì sao bốn thuật ngữ này quan trọng?

Khi dùng **Java Reflection API** để tra cứu annotation, hai câu hỏi “annotation có ở phần tử này không?” và “annotation được API trả về không?” chưa đủ chính xác. Java phân biệt bốn kiểu quan hệ giữa một annotation với phần tử được xét:

- **Directly present** — trực tiếp có mặt trên phần tử.
- **Indirectly present** — gián tiếp có mặt thông qua **container** của một repeatable annotation.
- **Present** — hiện diện, bao gồm quan hệ trực tiếp và quy tắc kế thừa giới hạn với class.
- **Associated** — liên kết, bao gồm trực tiếp, gián tiếp và quy tắc kế thừa giới hạn với class.

Bốn khái niệm này được định nghĩa trong giao diện chuẩn `java.lang.reflect.AnnotatedElement`; các phương thức `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType`, `getDeclaredAnnotationsByType` không có nghĩa hoàn toàn giống nhau.

Sự khác biệt rõ nhất khi kết hợp **`@Repeatable`** với **`@Inherited`**. Nếu đọc sai API, chương trình có thể bỏ sót annotation lặp, nhầm annotation được kế thừa với annotation được khai báo tại class con hoặc áp dụng sai cấu hình của class cha.

Bài này sử dụng các thuật ngữ theo nghĩa kỹ thuật của Java, không coi “present” là đồng nghĩa chung cho mọi kiểu tìm thấy annotation.

## 2. Điều kiện cơ bản: annotation có thể được đọc tại runtime

Để reflection nhìn thấy một annotation trên declaration hoặc type-use phù hợp, annotation cần được lưu giữ ở mức **`RetentionPolicy.RUNTIME`**:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}
```

Nếu **không có `@Retention`**, chính sách mặc định là **`CLASS`**. Annotation loại CLASS thường có thể được ghi vào class file, nhưng API `AnnotatedElement` không trả nó như annotation runtime. Vì vậy, khi phân tích kết quả `getAnnotation` hoặc `getAnnotationsByType`, trước tiên phải xác định retention.

**Một điểm về phạm vi:** quan hệ trực tiếp/gián tiếp/hiện diện/liên kết là cách đặc tả khả năng truy vấn annotation trên *một phần tử*; quan hệ kế thừa trong các định nghĩa này chỉ áp dụng với **class declaration** theo quy tắc `@Inherited`, không đồng nghĩa mọi method, field, parameter hoặc interface đều kế thừa annotation.

## 3. Directly present — annotation trực tiếp có mặt

Một annotation `A` thuộc loại `T` là **directly present** trên phần tử `E` khi `E` trực tiếp có annotation `A` trong metadata runtime của chính phần tử đó.

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Review {
    String value();
}

@Review("approved")
class Article {}
```

`@Review("approved")` được gắn trực tiếp vào `Article`. Với reflection:

```java
Review direct = Article.class.getDeclaredAnnotation(Review.class);
Review present = Article.class.getAnnotation(Review.class);
```

Cả hai có thể tìm thấy annotation ở class này vì nó **được khai báo trực tiếp**.

Từ “trực tiếp” mô tả **nguồn của annotation trong metadata**, không nói annotation được xử lý ngay lập tức. Nó không thực hiện kiểm duyệt article hay sinh logic `approved`.

Các API thường dùng để truy vấn trực tiếp:

- `getDeclaredAnnotation(T.class)`: trả một annotation **directly present** thuộc loại `T`, nếu không có trả `null`.
- `getDeclaredAnnotations()`: trả các annotation **directly present** trên chính phần tử, dưới dạng mảng `Annotation[]`; không tự bóc toàn bộ repeatable annotation nằm trong container.

`Declared` ở đây là truy vấn trên **phần tử đang xét**, không đi lên superclass. Đây là lý do cách tra cứu này hữu ích để phân biệt metadata khai báo cục bộ với metadata được kế thừa.

## 4. Indirectly present — annotation gián tiếp qua container

Một annotation loại `T` là **indirectly present** khi:

1. `T` là **repeatable annotation type**, được đánh dấu `@Repeatable(Container.class)`.
2. Annotation thuộc loại **container** của `T` trực tiếp có mặt trên phần tử.
3. Container có phần tử `value()` chứa annotation `T` đang xét.

Ví dụ:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}

@Tag("fast")
@Tag("safe")
class Job {}
```

Ở `Job`, hai `@Tag` trên cùng khai báo được Java biểu diễn thông qua container `@Tags`. Do đó, ở metadata runtime thông thường:

- `Tags.class` là annotation type **trực tiếp** của container trên `Job`.
- Hai giá trị `Tag` bên trong container là annotation **gián tiếp** trên `Job`.
- `Job.class.getDeclaredAnnotation(Tag.class)` trả `null` vì không có một `Tag` **directly present** riêng lẻ.
- `Job.class.getDeclaredAnnotation(Tags.class)` trả container.
- `Job.class.getDeclaredAnnotationsByType(Tag.class)` trả **hai `Tag`** bằng cách đọc xuyên qua container.

**Chú ý:** “Gián tiếp” ở đây có nghĩa rất cụ thể là **qua containing annotation type của `@Repeatable`**. Nó **không có nghĩa được kế thừa** từ superclass. Kế thừa thuộc hai khái niệm *present* và *associated*, được trình bày sau.

### Một lần @Tag so với hai lần @Tag

Nếu chỉ có:

```java
@Tag("single")
class SoloJob {}
```

thì thông thường `Tag` **directly present** trên `SoloJob`, không cần compiler tổng hợp container. Vì thế `getDeclaredAnnotation(Tag.class)` lấy được `Tag`; còn khi có hai `@Tag`, ta cần API `ByType` để đọc cả hai.

Nếu lập trình viên viết **container tường minh**:

```java
@Tags({@Tag("fast"), @Tag("safe")})
class ManualJob {}
```

thì hai `Tag` cũng là **indirectly present**. Khái niệm không phụ thuộc container được viết tường minh hay do compiler tổng hợp.

## 5. Present — annotation hiện diện

Một annotation `A` thuộc loại `T` là **present** trên phần tử `E` khi một trong hai điều kiện đúng:

1. `A` **directly present** trên `E`; hoặc
2. Không có annotation loại `T` **directly present** trên `E`, `E` là **class**, kiểu annotation `T` được đánh dấu **`@Inherited`**, và `A` **present** trên superclass của `E`.

Định nghĩa dùng tính chất **directly present** khi xét `T`; nó **không tự mở container**. Do đó, gọi `getAnnotation(Tag.class)` để tìm một repeatable annotation không có nghĩa API sẽ trả toàn bộ các `Tag` gián tiếp.

Ví dụ kế thừa một annotation đơn:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Owner {
    String value();
}

@Owner("team-core")
class BaseService {}

class ChildService extends BaseService {}
```

Với `ChildService.class`:

- `getDeclaredAnnotation(Owner.class)` là `null`: class con không khai báo `@Owner` trực tiếp.
- `getAnnotation(Owner.class)` lấy được `Owner("team-core")`: annotation **present** qua quy tắc `@Inherited`.
- `getDeclaredAnnotations()` không bao gồm `@Owner` được kế thừa từ class cha.

Nếu `ChildService` tự khai báo `@Owner("team-child")`, annotation cục bộ sẽ được ưu tiên khi tra cứu `Owner`.

**Phạm vi của `@Inherited`:** chỉ áp dụng tìm kiếm từ **class đến superclass**. Nó không làm annotation trên interface được kế thừa theo cách này; cũng không làm annotation method của superclass tự xuất hiện trên method override. Java reflection cần áp dụng quy tắc riêng cho từng phần tử.

## 6. Associated — annotation liên kết

Một annotation `A` thuộc loại `T` được coi là **associated** với phần tử `E` khi:

1. `A` **directly present hoặc indirectly present** trên `E`; hoặc
2. Không có annotation `T` nào trực tiếp **hoặc gián tiếp** trên `E`, `E` là **class**, `T` có `@Inherited`, và `A` **associated** với superclass.

Như vậy *associated* bổ sung khả năng **nhìn xuyên container** và vẫn hỗ trợ kế thừa có điều kiện. Đây là khái niệm dùng cho **`getAnnotationsByType(T.class)`**.

Ví dụ khái niệm:

```java
@Tag("read")
@Tag("write")
class RolesForAction {}
```

`getDeclaredAnnotationsByType(Tag.class)` và `getAnnotationsByType(Tag.class)` đều có thể trả hai giá trị nếu chúng có retention RUNTIME; cách thứ nhất chỉ kiểm tra chính phần tử, cách thứ hai còn có thể theo quy tắc `@Inherited` nếu annotation là inheritable và nguồn truy vấn là class.

Nếu class con tự khai báo các `Tag` trực tiếp hoặc gián tiếp, thì **các annotation cùng loại của class con được ưu tiên** khi xét *associated*; không tự cộng dồn tất cả `Tag` từ superclass vào kết quả. Nếu class con không có `Tag` trực tiếp hay gián tiếp, `getAnnotationsByType` mới có thể kế thừa kết quả của class cha theo quy tắc `@Inherited`.

### Present và associated không hoán đổi được

Với một annotation lặp có container, `getAnnotation(T.class)` xét **present**, còn `getAnnotationsByType(T.class)` xét **associated**. Đặc biệt, ở class con kế thừa annotation, việc có **container** cục bộ không đồng nghĩa class con có một annotation `T` trực tiếp.

Ví dụ nếu `@Tag` và container `@Tags` đều có `@Inherited`, class cha có một `@Tag("parent")`, còn class con có hai `@Tag("local-a")` và `@Tag("local-b")`, thì:

- `Child.class.getAnnotationsByType(Tag.class)` tìm thấy **hai Tag của chính Child** (gián tiếp qua container); nó không cộng thêm `parent`.
- `Child.class.getAnnotation(Tag.class)` vẫn có thể trả `Tag("parent")` được kế thừa, bởi ở Child **không có Tag directly present**, chỉ có container trực tiếp. Đây là hậu quả của định nghĩa chính xác về *present*, khác với *associated*.

Đây là trường hợp nên **cố ý chọn API theo nhu cầu** và không diễn giải kết quả của một phương thức thay cho phương thức kia.

## 7. Bảng ánh xạ bốn thuật ngữ với Java Reflection

| API trên `AnnotatedElement` | Loại quan hệ được truy vấn | Có mở container `@Repeatable`? | Có xét superclass nhờ `@Inherited`? |
| --- | --- | --- | --- |
| `getDeclaredAnnotation(T.class)` | **Directly present** | Không | Không |
| `getDeclaredAnnotations()` | **Directly present** (tất cả loại) | Không | Không |
| `getAnnotation(T.class)` | **Present** | Không | Có, chỉ class và điều kiện phù hợp |
| `getAnnotations()` | **Present** (tất cả loại) | Không mở container thành `T[]` | Có, chỉ class và điều kiện phù hợp |
| `getDeclaredAnnotationsByType(T.class)` | **Directly + indirectly present** | Có | Không |
| `getAnnotationsByType(T.class)` | **Associated** | Có | Có, chỉ class và điều kiện phù hợp |

**Cách chọn nhanh:**

- Cần đúng **một annotation khai báo trực tiếp**? Dùng `getDeclaredAnnotation`.
- Cần lấy **nhiều annotation cùng loại** trên chính phần tử? Dùng `getDeclaredAnnotationsByType`.
- Cần một annotation có tính `@Inherited` theo quan hệ class? Dùng `getAnnotation`, nhớ rằng API này không bóc các phần tử repeatable gián tiếp.
- Cần **nhiều annotation cùng loại** và muốn áp dụng kế thừa khi hợp lệ? Dùng `getAnnotationsByType`.

`getAnnotations()` và `getDeclaredAnnotations()` trả mảng gồm các annotation type trực tiếp/hiện diện tương ứng, bao gồm **container** nếu container chính là annotation trực tiếp. Không nên dùng hai API đó rồi giả định mọi repeatable annotation bên trong container đã thành phần tử riêng của mảng.

## 8. Ví dụ Java 17+ hoàn chỉnh: bốn quan hệ trong một chương trình

Tạo file **AnnotationLookupKindsDemo.java** với toàn bộ nội dung sau. Ví dụ chỉ dùng Java SE, bao gồm **repeatable annotation**, **container**, **`@Inherited`** và các lời gọi reflection để so sánh.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("base")
class Base {}

class InheritedChild extends Base {}

@Label("first")
@Label("second")
class Repeated {}

@Labels({@Label("manual-a"), @Label("manual-b")})
class ExplicitContainer {}

public class AnnotationLookupKindsDemo {
    private static String values(Label[] annotations) {
        return Arrays.stream(annotations)
                .map(Label::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) {
        System.out.println("base direct="
                + Base.class.getDeclaredAnnotation(Label.class).value());

        System.out.println("child direct="
                + (InheritedChild.class.getDeclaredAnnotation(Label.class)
                    != null));
        System.out.println("child present="
                + InheritedChild.class.getAnnotation(Label.class).value());
        System.out.println("child associated="
                + values(InheritedChild.class.getAnnotationsByType(Label.class)));

        System.out.println("repeated direct="
                + (Repeated.class.getDeclaredAnnotation(Label.class) != null));
        System.out.println("repeated container="
                + (Repeated.class.getDeclaredAnnotation(Labels.class) != null));
        System.out.println("repeated declaredByType="
                + values(Repeated.class.getDeclaredAnnotationsByType(Label.class)));

        System.out.println("explicit associated="
                + values(ExplicitContainer.class.getAnnotationsByType(Label.class)));
    }
}
```

Tại thư mục chứa file, sử dụng JDK 17 hoặc mới hơn:

```bash
javac AnnotationLookupKindsDemo.java
java AnnotationLookupKindsDemo
```

Stdout:

```text
base direct=base
child direct=false
child present=base
child associated=base
repeated direct=false
repeated container=true
repeated declaredByType=first,second
explicit associated=manual-a,manual-b
```

**Đọc từng kết quả:**

1. `Base` có một `@Label("base")` trực tiếp, nên `getDeclaredAnnotation` trả annotation này.
2. `InheritedChild` không khai báo `@Label`, nên `getDeclaredAnnotation` trả `null`; điều kiện boolean in `false`.
3. `Label` có `@Inherited`, cho phép `getAnnotation` trên **class con** nhìn lên `Base`. Đây là annotation **present** qua kế thừa.
4. `getAnnotationsByType` trên `InheritedChild` cũng có thể truy về class cha vì không có `Label` trực tiếp hay gián tiếp tại class con, và `Label` là inheritable.
5. `Repeated` có hai `@Label` cùng loại. Metadata được biểu diễn bằng container, nên không có một `Label` directly present; nhưng `Labels` directly present. Vì vậy hai boolean lần lượt là `false` và `true`.
6. `getDeclaredAnnotationsByType(Label.class)` bóc container thành `first,second` đúng thứ tự giá trị annotation trong container.
7. `ExplicitContainer` khai báo container tường minh. `getAnnotationsByType` vẫn đọc được cả hai `Label` bên trong, chứng tỏ *indirectly present* không chỉ áp dụng khi compiler tự tổng hợp container.

**Điều kiện để ví dụ hoạt động:** `Label` và `Labels` phải cùng có retention `RUNTIME` để chương trình đọc dữ liệu ở runtime, và với tính kế thừa repeatable annotation, container cần có `@Inherited` tương thích. `@Target(TYPE)` cho phép gắn annotation vào class.

## 9. Vai trò của @Repeatable, @Inherited và @Retention

### 9.1. @Repeatable kiểm soát khả năng lặp và container

`@Repeatable(Labels.class)` cho phép một loại annotation xuất hiện nhiều lần trên cùng khai báo. Container `Labels` có phần tử `Label[] value()`. Chính container tạo điều kiện cho khái niệm **indirectly present**.

`@Repeatable` không làm mỗi `@Label` trở thành một lần thực thi riêng; nó chỉ xác định cách biểu diễn nhiều annotation cùng loại.

### 9.2. @Inherited kiểm soát quy tắc kế thừa trên class

`@Inherited` chỉ liên quan việc **tra cứu annotation của class qua superclass**. Không tự áp dụng cho:

- Annotation được khai báo trên **method**, kể cả method override ở subclass.
- Annotation trên **field** hoặc **formal parameter**.
- Annotation trên **interface** chỉ vì một class `implements` interface đó.

Nếu một repeatable annotation type được đánh dấu `@Inherited`, container phải đáp ứng ràng buộc tương thích về `@Inherited` để khai báo repeatable hợp lệ.

### 9.3. @Retention quyết định annotation có mặt ở runtime hay không

Không khai báo `@Retention` nghĩa là mặc định `CLASS`. Annotation vẫn có thể hữu ích ở compile time hoặc công cụ đọc class file, nhưng không hiện ra ở kết quả truy vấn `AnnotatedElement` như các ví dụ dùng reflection.

Khi thiết kế repeatable annotation đọc bằng reflection, thông thường khai báo `@Retention(RUNTIME)` cho **cả annotation lặp và container**.

## 10. Những tình huống dễ hiểu sai

**Tình huống 1 — Một annotation trực tiếp nhưng không xuất hiện qua reflection.** Kiểm tra `@Retention`: nếu là `SOURCE` hoặc `CLASS`, đừng kỳ vọng các API runtime trả về nó.

**Tình huống 2 — Có hai @Tag trong source nhưng getDeclaredAnnotation(Tag.class) là null.** Với repeatable annotation, compiler có thể lưu chúng gián tiếp qua container. Hãy dùng `getDeclaredAnnotationsByType(Tag.class)`.

**Tình huống 3 — Container có mặt nhưng không thấy các annotation con trong getDeclaredAnnotations().** `getDeclaredAnnotations()` trả container như một annotation trực tiếp; muốn bóc các phần tử, dùng API `ByType`.

**Tình huống 4 — getAnnotation trên class con trả annotation của class cha.** Nếu kiểu annotation có `@Inherited` và class con không có annotation cùng loại trực tiếp, đây là kết quả của quy tắc *present*. Truy vấn `getDeclaredAnnotation` nếu chỉ muốn metadata được khai báo trên class con.

**Tình huống 5 — Mong getAnnotationsByType luôn gộp tất cả annotation trong cây kế thừa.** Quy tắc *associated* ưu tiên annotation trực tiếp hoặc gián tiếp của class đang xét; chỉ xét superclass khi tại class hiện tại không có annotation cùng loại theo hai dạng đó.

**Tình huống 6 — Dùng @Inherited trên method annotation để nhận dữ liệu từ overridden method.** `@Inherited` chỉ hoạt động với quy tắc class, không tự động áp dụng trên phương thức.

**Tình huống 7 — Nhầm indirectly present với inherited.** “Indirectly” liên quan `@Repeatable` **container**; “inherited” liên quan `@Inherited` và quan hệ class/superclass.

**Tình huống 8 — Cho rằng getAnnotationsByType chỉ lấy annotation được khai báo trực tiếp.** `getAnnotationsByType` kiểm tra *associated*, gồm cả repeatable container và kế thừa khi hợp lệ. Muốn loại trừ kế thừa, dùng `getDeclaredAnnotationsByType`.

**Tình huống 9 — Truyền annotation type sai package.** Hai annotation cùng tên ngắn nhưng ở hai package khác nhau là hai loại khác nhau; `getAnnotation` nhận đối tượng `Class<T>` của đúng annotation type.

**Tình huống 10 — Mong annotation tự áp dụng cấu hình runtime.** Các API ở đây chỉ **truy xuất metadata**; hệ thống vẫn phải triển khai logic riêng để dùng metadata vào validation, routing, phân quyền, logging hoặc các tác vụ nghiệp vụ.

## 11. Quy trình lựa chọn API khi xây thư viện

Giả sử một framework tự viết cần đọc `@Rule` từ một class:

1. Mở định nghĩa `@Rule`: xem `@Retention(RUNTIME)` có hay không.
2. Kiểm tra `@Repeatable`: nếu `@Rule` có thể lặp, cần hỗ trợ container; ưu tiên `getAnnotationsByType(Rule.class)` hoặc `getDeclaredAnnotationsByType(Rule.class)`.
3. Xác định có muốn kế thừa từ superclass không: dùng `Declared` khi chỉ đọc phần tử hiện tại; dùng không-`Declared` để thực hiện các quy tắc kế thừa Java phù hợp.
4. Kiểm tra `@Inherited` (chỉ có ý nghĩa như mô tả cho class) và container tương thích.
5. Nếu phần tử được xét không phải class, đừng suy rằng annotation sẽ tự được kế thừa từ một phần tử cùng tên ở nơi khác.
6. Phân biệt **không tìm thấy**, **một giá trị**, **nhiều giá trị**; API `ByType` trả mảng rỗng nếu không có annotation phù hợp.

Chọn đúng quan hệ cần tìm sẽ khiến kết quả ổn định hơn khi sau này annotation type được mở rộng thành repeatable hoặc được cấu hình kế thừa.

## 12. Bài tập tự kiểm tra

1. Thêm `@Label("third")` lên `Repeated`; dự đoán `getDeclaredAnnotation(Label.class)`, kết quả container và `getDeclaredAnnotationsByType(Label.class)`.
2. Đặt một `@Label("local")` trực tiếp lên `InheritedChild`. Quan sát `getDeclaredAnnotation`, `getAnnotation`, `getAnnotationsByType` để giải thích cơ chế ưu tiên annotation cục bộ.
3. Đặt hai `@Label` trên `InheritedChild` thay vì một; dự đoán sự khác biệt giữa `getAnnotation(Label.class)` và `getAnnotationsByType(Label.class)` dựa vào khái niệm *present* và *associated*.
4. Xóa `@Inherited` khỏi `Label` **và container `Labels`** rồi biên dịch lại. Dự đoán kết quả truy vấn trên class `InheritedChild`; giải thích vì sao không còn thừa hưởng annotation.
5. Thay retention `RUNTIME` của cả `Label` và `Labels` thành `CLASS`. Quan sát kết quả khi dùng reflection, rồi dùng `javap -v` để khảo sát metadata class file.
6. Thay lời gọi `getDeclaredAnnotationsByType(Label.class)` trên `Repeated` bằng `getDeclaredAnnotations()`. Nhận diện container trong mảng kết quả và giải thích vì sao nó không được tách thành hai annotation `Label`.
7. Tạo method `@Label` tương tự sau khi điều chỉnh `@Target(METHOD)` cho cả hai annotation; so sánh việc `@Inherited` có giúp một method override tự nhận annotation hay không.

**Điểm cần nhớ:** *Directly present* là annotation được lưu trực tiếp; *indirectly present* đến từ container của repeatable annotation; *present* thêm cơ chế kế thừa giới hạn trên class cho annotation trực tiếp; còn *associated* bao gồm cả annotation lặp qua container và kế thừa khi được phép. Java Reflection ánh xạ những khái niệm này vào các API riêng. Với repeatable annotations, dùng **`getAnnotationsByType`** khi cần đầy đủ các giá trị liên kết và **`getDeclaredAnnotationsByType`** khi chỉ cần những giá trị của phần tử hiện tại.
