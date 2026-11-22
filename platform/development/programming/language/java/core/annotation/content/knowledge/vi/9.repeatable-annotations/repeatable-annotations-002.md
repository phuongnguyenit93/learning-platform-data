# @Repeatable và kiểu annotation chứa trong Java

## 1. Annotation lặp là gì?

Trong Java, một annotation thường được gắn **một lần cho mỗi phần tử chương trình**. Từ Java 8, một kiểu annotation có thể được khai báo là **repeatable annotation** bằng meta-annotation **`@Repeatable`**, cho phép sử dụng **cùng một loại annotation nhiều lần tại cùng một vị trí hợp lệ**.

Ví dụ, một phương thức có thể có hai metadata cùng loại:

```java
@Tag("performance")
@Tag("security")
void check() {}
```

Cú pháp trên hợp lệ khi `Tag` được định nghĩa là annotation lặp được. Hai dòng mang hai giá trị khác nhau cho **cùng một khai báo `check()`**. Chúng không phải hai lời gọi phương thức và không khiến `check()` chạy hai lần.

Để hỗ trợ cú pháp đó, Java yêu cầu khai báo **kiểu annotation chứa (containing annotation type, còn gọi là container)**. Ví dụ:

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

Có hai kiểu annotation liên quan:

- **`Tag`**: loại annotation cần lặp, có một phần tử `String value()`.
- **`Tags`**: loại annotation chứa, có phần tử `Tag[] value()`, nghĩa là một mảng `Tag`.
- **`@Repeatable(Tags.class)`**: khai báo với Java rằng các lần sử dụng `Tag` lặp trên cùng vị trí được chứa bởi kiểu `Tags`.

`@Repeatable` là meta-annotation chuẩn thuộc `java.lang.annotation`; `Tag` và `Tags` trong ví dụ là hai annotation tự định nghĩa. Nếu không có khai báo container hợp lệ, việc lặp trực tiếp hai `@Tag` trên cùng khai báo sẽ lỗi biên dịch.

## 2. Vì sao cần kiểu annotation chứa?

Một Java class file biểu diễn annotation bằng metadata có cấu trúc. Khi lập trình viên sử dụng nhiều `@Tag` trên cùng khai báo, compiler có thể **đóng gói các lần lặp vào một annotation container `@Tags`** trong metadata của phần tử đó.

Có thể hình dung:

```java
@Tag("performance")
@Tag("security")
class Service {}
```

Tương ứng về mặt biểu diễn các giá trị:

```java
@Tags({
    @Tag("performance"),
    @Tag("security")
})
class Service {}
```

Hai đoạn trên minh họa **hai cách viết thay thế nhau** cho một class; không đặt cả hai dạng lên cùng class. Khi có nhiều annotation `Tag` trực tiếp, Java sử dụng container để mô tả các lần xuất hiện ấy. Điều này giải thích vì sao khi dùng reflection, **API đọc trực tiếp `Tag` và API đọc theo loại `Tag` có thể cho kết quả khác nhau**.

Trong thực tế, ta thường viết dạng `@Tag` nhiều lần vì dễ đọc hơn. Kiểu chứa vẫn phải được định nghĩa đúng hợp đồng và có thể được sử dụng trực tiếp khi cần.

### 2.1. Container là một kiểu annotation bình thường

Kiểu chứa không phải array field của Java class và cũng không phải một object wrapper được tạo bằng `new`. Nó là một **annotation type** khai báo bằng `@interface`, với một phần tử đặc biệt tên **`value`**, có kiểu trả về chính xác là **mảng một chiều của annotation được lặp**.

```java
@interface Tags {
    Tag[] value();
}
```

`Tag[] value()` cho phép lưu 0, 1 hoặc nhiều giá trị `@Tag(...)` nếu dùng container tường minh. Tuy vậy, `@Repeatable(Tags.class)` chỉ cần thiết khi muốn dùng dạng **nhiều `@Tag` trực tiếp trên cùng khai báo**, chứ không phải để một phần tử annotation bình thường nhận mảng giá trị.

### 2.2. Khai báo tối thiểu có thể biên dịch

Đoạn sau đủ thể hiện quan hệ cặp annotation lặp và container:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
}

@Label("first")
@Label("second")
class Note {}
```

Các annotation ở đây không khai báo `@Retention`, nên **mặc định là `RetentionPolicy.CLASS`**. Chúng hợp lệ về cú pháp và được ghi vào class file ở những vị trí được hỗ trợ; nếu muốn dùng Java reflection lúc chạy, cần quy định `RUNTIME` như ví dụ hoàn chỉnh ở mục 5.

## 3. Hợp đồng bắt buộc giữa annotation lặp và container

`@Repeatable(Container.class)` không thể trỏ đến bất kỳ annotation type nào. Container phải thỏa nhiều điều kiện mà compiler kiểm tra.

### 3.1. Phải có phần tử value() đúng kiểu mảng

Giả sử annotation cần lặp tên `Role`:

```java
@interface Roles {
    Role[] value();
}
```

**`value()` phải trả về `Role[]`**. Các dạng như `Role value()`, `String[] value()`, `List<Role> value()` đều sai hợp đồng. `List<Role>` còn không phải kiểu phần tử hợp lệ của annotation trong Java.

Container có thể có thêm phần tử, nhưng **các phần tử khác `value` phải có giá trị mặc định**. Ví dụ hợp lệ:

```java
@interface Roles {
    Role[] value();
    String source() default "manual";
}
```

Khi compiler tổng hợp container từ các `@Role` lặp, giá trị `source` có thể dùng giá trị mặc định. Nếu `source()` thiếu `default`, container không hợp lệ làm kiểu chứa cho `Role`.

### 3.2. Retention của container phải tương thích

Khi một annotation lặp `@Role` có `@Retention(RUNTIME)`, container phải được lưu đủ lâu để thông tin không bị mất trước runtime. Cách thông dụng, dễ hiểu và an toàn nhất là **đặt cùng chính sách `RUNTIME` cho cả hai**:

```java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Roles {
    Role[] value();
}
```

Quy tắc tương thích cần nhớ là **container không được có retention ngắn hơn annotation lặp**:

| Retention của annotation lặp | Retention container cho phép về thời hạn |
| --- | --- |
| `SOURCE` | `SOURCE`, `CLASS` hoặc `RUNTIME` |
| `CLASS` | `CLASS` hoặc `RUNTIME` |
| `RUNTIME` | `RUNTIME` |

Nếu annotation lặp `RUNTIME` nhưng container `CLASS`, chương trình **không biên dịch** với khai báo `@Repeatable` đó. Khi không khai báo `@Retention`, mặc định của annotation type là `CLASS`; điều này cũng áp dụng cho container.

### 3.3. Target của container phải cho phép các vị trí của annotation lặp

Nếu `Role` chỉ dùng trên phương thức, hãy cho cả hai dùng `METHOD`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Target(ElementType.METHOD)
@interface Roles {
    Role[] value();
}
```

Khi đó:

```java
class AccountService {
    @Role("READ")
    @Role("WRITE")
    void update() {}
}
```

là cách sử dụng hợp lệ. Nhưng nếu container không được phép áp dụng tại vị trí mà annotation lặp cho phép (ví dụ container chỉ có `TYPE`, còn annotation lặp có `METHOD`), compiler sẽ từ chối cấu hình `@Repeatable` không tương thích.

Đặt **cùng `@Target`** cho cả hai là lựa chọn rõ ràng trong ví dụ thông thường. Java có quy tắc tương thích chi tiết đối với từng nhóm đích như `TYPE`, `ANNOTATION_TYPE`, `TYPE_USE` và `TYPE_PARAMETER`; khi thiết kế container đa đích cần đối chiếu ngữ nghĩa áp dụng, thay vì suy rằng mọi tập target tùy ý đều tương đương.

### 3.4. @Documented và @Inherited phải tương thích

Khi annotation lặp được khai báo `@Documented`, container **cũng cần khai báo `@Documented`**. Khi annotation lặp được khai báo `@Inherited`, container **cũng cần khai báo `@Inherited`**.

`@Documented` kiểm soát việc annotation xuất hiện trong tài liệu do công cụ hỗ trợ tạo. `@Inherited` tác động đến việc tra cứu annotation từ superclass đối với annotation trên khai báo **class**, theo các điều kiện của Java; nó không khiến annotation trên method hoặc field tự được kế thừa theo cùng quy tắc.

Cả hai meta-annotation đều **không thay thế `@Retention`**. Nếu cần đọc annotation lặp qua reflection, vẫn phải quan tâm tới retention của annotation lặp và container.

## 4. Cách sử dụng trực tiếp và dạng container

Có ba cách quan sát cùng một loại `Tag`:

```java
// Cách A: một annotation trực tiếp
@Tag("one")
class SingleTag {}

// Cách B: lặp annotation trực tiếp
@Tag("one")
@Tag("two")
class RepeatedTags {}

// Cách C: dùng container tường minh
@Tags({@Tag("one"), @Tag("two")})
class ExplicitContainer {}
```

Giả sử `Tag` và `Tags` được khai báo như ở ví dụ mục 5 với retention `RUNTIME`. Các trường hợp trên có ý nghĩa khi dùng reflection:

| Cách khai báo | `getDeclaredAnnotation(Tag.class)` | `getDeclaredAnnotation(Tags.class)` | `getDeclaredAnnotationsByType(Tag.class)` |
| --- | --- | --- | --- |
| Một `@Tag` | Trả về `Tag` | Thường trả về `null` | Mảng có 1 `Tag` |
| Hai `@Tag` trực tiếp | Thường `null`: chúng được chứa gián tiếp | Trả về container `Tags` | Mảng có 2 `Tag` |
| Một `@Tags` chứa 2 `@Tag` | `null` | Trả về `Tags` | Mảng có 2 `Tag` |

Cụm **trực tiếp (directly present)** và **gián tiếp (indirectly present)** là quan trọng. Khi hai `@Tag` được biểu diễn bằng container, reflection trực tiếp trên cùng phần tử không nhất thiết có một đối tượng `Tag` đứng riêng. API `getDeclaredAnnotationsByType(Tag.class)` có chức năng mở container và trả các phần tử `Tag`.

Không nên viết cả `@Tag(...)` lẫn container `@Tags(...)` theo cách làm cùng loại vừa hiện diện trực tiếp vừa gián tiếp trên **cùng một phần tử**; Java không cho phép tổ hợp đó cho cùng repeatable type trên cùng declaration.

## 5. Ví dụ Java 17+ hoàn chỉnh: @Repeatable, container và reflection

Tạo file **RepeatableAnnotationDemo.java** với nội dung đầy đủ sau. Chương trình chỉ dùng JDK, không cần thư viện ngoài.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}

@Tag("core")
@Tag("annotation")
class Lesson {
    @Tag("single")
    public void read() {}
}

public class RepeatableAnnotationDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Tag[] classTags = Lesson.class.getDeclaredAnnotationsByType(Tag.class);

        System.out.println("class count=" + classTags.length);
        for (Tag tag : classTags) {
            System.out.println("tag=" + tag.value());
        }

        Tag direct = Lesson.class.getDeclaredAnnotation(Tag.class);
        Tags container = Lesson.class.getDeclaredAnnotation(Tags.class);
        System.out.println("direct Tag? " + (direct != null));
        System.out.println("container? " + (container != null));
        System.out.println("container count=" + container.value().length);

        Method method = Lesson.class.getDeclaredMethod("read");
        Tag methodTag = method.getDeclaredAnnotation(Tag.class);
        System.out.println("method tag=" + methodTag.value());
    }
}
```

Biên dịch và chạy tại thư mục chứa file bằng JDK 17+:

```bash
javac RepeatableAnnotationDemo.java
java RepeatableAnnotationDemo
```

Kết quả stdout:

```text
class count=2
tag=core
tag=annotation
direct Tag? false
container? true
container count=2
method tag=single
```

**Giải thích kết quả:**

1. `@Tag("core")` và `@Tag("annotation")` cùng đặt trên class `Lesson` nhờ `@Repeatable(Tags.class)`. Java sử dụng container để biểu diễn các lần lặp đó.
2. `getDeclaredAnnotationsByType(Tag.class)` đọc các `Tag` trực tiếp và gián tiếp qua container. Kết quả mảng có hai phần tử; trong trường hợp compiler tổng hợp từ nhiều dòng `@Tag`, thứ tự phản ánh thứ tự các annotation lặp được khai báo.
3. `Lesson.class.getDeclaredAnnotation(Tag.class)` trả về `null` vì khi lặp nhiều lần, `Tag` được chứa gián tiếp trong `Tags`. `getDeclaredAnnotation(Tags.class)` lấy được container.
4. Container có `value()` trả về mảng gồm hai `Tag`, nên `container.value().length` bằng 2.
5. Phương thức `read()` chỉ mang **một `@Tag("single")`**; đây là annotation trực tiếp, nên `getDeclaredAnnotation(Tag.class)` lấy được `Tag`.

Nếu muốn một API nhất quán cho các trường hợp 0, 1 hoặc nhiều `Tag`, nên ưu tiên **`getAnnotationsByType(Tag.class)`** (bao gồm các quy tắc kế thừa khi áp dụng được) hoặc **`getDeclaredAnnotationsByType(Tag.class)`** (chỉ xem khai báo trên phần tử hiện tại).

### 5.1. Reflection biết container từ đâu?

Một chương trình có thể đọc meta-annotation `@Repeatable` trên annotation type:

```java
// Đoạn bổ sung sau khi đã định nghĩa Tag và Tags:
Repeatable info = Tag.class.getAnnotation(Repeatable.class);
Class<?> containerType = info.value(); // Tags.class
```

`info.value()` chứa **kiểu container**, không phải mảng các `Tag` đã sử dụng trên một class cụ thể. Muốn đọc các giá trị `Tag` của class `Lesson`, dùng `getAnnotationsByType(Tag.class)` trên class ấy.

## 6. getAnnotation, getAnnotationsByType và getDeclaredAnnotationsByType

Với Java Reflection API, chọn đúng phương thức là yếu tố then chốt:

- **`getAnnotation(Tag.class)`**: trả về annotation `Tag` hiện diện trực tiếp hoặc hiện diện thông qua kế thừa theo ngữ nghĩa Java; **không mở container để trả nhiều `Tag`**. Kết quả là một `Tag` hoặc `null`.
- **`getAnnotationsByType(Tag.class)`**: trả về **mảng `Tag[]`**, xét cả các lần trực tiếp và gián tiếp qua container, cùng quy tắc kế thừa khi type được đánh dấu `@Inherited` ở khai báo class.
- **`getDeclaredAnnotation(Tag.class)`**: truy vấn annotation loại `Tag` hiện diện trực tiếp ở phần tử hiện tại, không tìm kế thừa và không trải container.
- **`getDeclaredAnnotationsByType(Tag.class)`**: trả về `Tag[]` ở **chính phần tử đang xét**, mở container nếu có, không lấy từ superclass.

Ví dụ một class có hai `@Tag` sẽ thường cho:

```java
// Mã minh họa trong bối cảnh class Lesson của mục 5
Lesson.class.getAnnotation(Tag.class);                  // null
Lesson.class.getAnnotationsByType(Tag.class).length;    // 2
Lesson.class.getAnnotation(Tags.class);                 // Tags
Lesson.class.getDeclaredAnnotationsByType(Tag.class).length; // 2
```

Hai method có tên gần giống nhưng khác `ByType` **không hoán đổi được**. Đây là nguồn gây lỗi phổ biến: người viết code dùng `getAnnotation(Tag.class)` và tưởng rằng `@Tag` không tồn tại vì kết quả `null`.

### 6.1. Có phải container được Java tự tạo?

Java compiler **có thể tổng hợp một *lần sử dụng* container** khi gặp nhiều annotation lặp, nhưng **nó không tự tạo định nghĩa kiểu container** `Tags`. Lập trình viên hoặc thư viện phải định nghĩa `@interface Tags` trước, rồi truyền `Tags.class` vào `@Repeatable`.

Lúc chỉ có một `@Tag`, compiler có thể giữ nó như annotation trực tiếp, không cần tổng hợp một container. Vì vậy đừng giả định mọi phần tử có một `@Tag` đều có `@Tags`. Khi muốn đọc một cách thống nhất, dùng `getAnnotationsByType(Tag.class)`.

## 7. Retention, target và kế thừa trong annotation lặp

### 7.1. Nếu thiếu @Retention

Giả sử:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Markers.class)
@interface Marker {
    String value();
}

@interface Markers {
    Marker[] value();
}
```

Cả `Marker` và `Markers` đều mặc định `RetentionPolicy.CLASS`. Các lần sử dụng `@Marker` có thể được ghi vào class file, nhưng **Java reflection lúc chạy không đọc chúng như RUNTIME annotation**. Lỗi thiết kế thường gặp là đặt `@Retention(RUNTIME)` cho `Marker` rồi quên nâng retention của container cho tương thích.

Khi cần reflection runtime, khai báo `@Retention(RetentionPolicy.RUNTIME)` trên **cả hai kiểu** như trong ví dụ hoàn chỉnh.

### 7.2. Target của annotation lặp và container

Lặp `@Tag` trên class/method không hợp lệ nếu `Tag` không được phép áp dụng ở những vị trí này, hoặc container `Tags` không tương thích về target. Cách đơn giản là đặt cùng:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
```

cho cả hai. Nếu `Tag` chỉ có `METHOD`, không thể sử dụng `@Tag` trên class chỉ vì container lại cho phép `TYPE`.

### 7.3. @Inherited có tác dụng giới hạn

Nếu muốn **class con** có thể thừa hưởng metadata lặp từ class cha qua các API phù hợp, annotation lặp có thể dùng `@Inherited` và container cũng phải dùng `@Inherited`. Đồng thời cần `RUNTIME` retention nếu định đọc qua reflection.

Ví dụ minh họa độc lập (đã có `Tag`, `Tags` cùng được đánh dấu `@Inherited`, với `RUNTIME`):

```java
@Tag("parent-1")
@Tag("parent-2")
class Parent {}

class Child extends Parent {}
```

Trong trường hợp trên, `Child.class.getAnnotationsByType(Tag.class)` có thể trả về hai `Tag` thừa hưởng từ `Parent`, theo quy tắc của `@Inherited`.

Ngược lại, nếu `Child` **tự khai báo một hoặc nhiều `@Tag`** cùng loại, các annotation của chính `Child` được ưu tiên khi tra cứu loại này qua `getAnnotationsByType`, thay vì tự động cộng dồn với các `Tag` của `Parent`.

**`@Inherited` không làm annotation phương thức trên superclass tự thừa hưởng qua method override**, và không tự động áp dụng trên interface. Đó là các hợp đồng riêng của Java về kế thừa annotation ở cấp class.

## 8. So sánh @Repeatable với mảng annotation làm giá trị

Đây là hai mô hình khác nhau:

### A. Repeatable annotation trên cùng phần tử

```java
@Role("EDITOR")
@Role("REVIEWER")
class DocumentService {}
```

Cả hai `@Role` gắn **trực tiếp lên khai báo class**, chỉ hợp lệ khi `Role` có `@Repeatable(Roles.class)` với container thích hợp.

### B. Mảng annotation nằm trong một annotation lớn

```java
@interface Permission {
    String name();
}

@interface AccessPolicy {
    Permission[] permissions();
}

@AccessPolicy(permissions = {
    @Permission(name = "EDITOR"),
    @Permission(name = "REVIEWER")
})
class DocumentService {}
```

Ở trường hợp B, class chỉ gắn **một `@AccessPolicy`**. Hai `@Permission` là **giá trị phần tử `permissions()`**, vì thế `Permission` không cần `@Repeatable`.

**Chọn mô hình theo ý nghĩa dữ liệu**: nếu các mục độc lập cần đặt lặp trực tiếp trên khai báo, `@Repeatable` giúp gọn source; nếu chúng là thành phần của một cấu hình lớn hơn, mảng annotation-valued element có thể diễn tả quan hệ cha-con rõ hơn.

## 9. Lỗi thường gặp và cách xử lý

**Lỗi 1 — Lặp annotation chưa khai báo @Repeatable.** Viết hai `@Tag` cùng trên một class khi `Tag` không có `@Repeatable` sẽ lỗi biên dịch. Khai báo container hợp lệ rồi gắn `@Repeatable(Container.class)`.

**Lỗi 2 — Container có sai chữ ký value().** `String[] value()`, `Tag value()` hoặc `List<Tag> value()` đều không đáp ứng yêu cầu `Tag[] value()`.

**Lỗi 3 — Container có phần tử bắt buộc khác value().** `String category();` không có default sẽ khiến compiler không thể tổng hợp container hợp lệ. Thêm default hợp lệ hoặc bỏ phần tử đó nếu không cần.

**Lỗi 4 — Retention của container ngắn hơn annotation lặp.** Nếu `Tag` là RUNTIME mà `Tags` là CLASS, compiler từ chối định nghĩa repeatable annotation. Cho container retention tương thích, thường là cùng RUNTIME.

**Lỗi 5 — Target không tương thích.** Container phải có khả năng áp dụng ở các đích cần thiết của annotation lặp; đặt `@Target` rõ ràng cho cả hai.

**Lỗi 6 — Bỏ sót @Documented hoặc @Inherited trên container.** Khi annotation lặp có một trong các meta-annotation này, container phải đáp ứng quy tắc tương ứng.

**Lỗi 7 — Dùng getAnnotation(Tag.class) để tìm tất cả Tag.** Với nhiều `@Tag`, dữ liệu có thể nằm gián tiếp trong `@Tags`; dùng `getAnnotationsByType(Tag.class)` hoặc `getDeclaredAnnotationsByType(Tag.class)`.

**Lỗi 8 — Cho rằng compiler tự sinh @interface container.** Java tổng hợp *giá trị sử dụng container* khi cần, nhưng định nghĩa `@interface Tags` là trách nhiệm của người thiết kế annotation.

**Lỗi 9 — Kết hợp trực tiếp @Tag và @Tags trên cùng phần tử.** Khi làm `Tag` vừa trực tiếp vừa gián tiếp hiện diện trên cùng phần tử, Java không chấp nhận cấu hình đó. Chọn một kiểu khai báo.

**Lỗi 10 — Tưởng @Repeatable thực thi tác vụ nhiều lần.** Nó chỉ cho phép lưu nhiều giá trị metadata. Muốn thực thi nhiều quy tắc, một thành phần phải đọc `Tag[]` rồi tự xử lý từng giá trị.

**Lỗi 11 — Quên RUNTIME retention khi dùng reflection.** Annotation lặp mặc định CLASS thì reflection thông thường không thấy, kể cả khi khai báo repeatable/container về mặt cú pháp hoàn toàn hợp lệ.

**Lỗi 12 — Nghĩ kế thừa annotation lặp sẽ luôn cộng dồn.** `@Inherited` chỉ liên quan quy tắc annotation của class, có ưu tiên khi class con tự khai báo cùng loại và không áp dụng đơn giản lên method override.

## 10. Bài tập thực hành

1. **Thay đổi số lượng:** Trong `RepeatableAnnotationDemo.java`, thêm `@Tag("reflection")` lên `Lesson`, biên dịch lại và dự đoán số lượng, thứ tự các dòng `tag=` và `container count=`.
2. **Tự kiểm tra reflection:** Đổi `getDeclaredAnnotationsByType(Tag.class)` thành `getDeclaredAnnotation(Tag.class)`. Giải thích vì sao hai API không trả về cùng kiểu dữ liệu và vì sao kết quả trực tiếp có thể là `null` khi lặp.
3. **Thử bỏ container:** Xóa định nghĩa `@interface Tags` nhưng giữ `@Repeatable(Tags.class)`. Ghi nhận lỗi biên dịch do container type không còn được định nghĩa.
4. **Thử sai value():** Thay `Tag[] value()` của `Tags` thành `String[] value()`, rồi giải thích hợp đồng compiler yêu cầu.
5. **Thử sai retention:** Giữ `@Retention(RUNTIME)` trên `Tag` nhưng đổi `Tags` thành `@Retention(CLASS)`. Xác định lỗi biên dịch và sửa bằng retention phù hợp.
6. **Viết container tường minh:** Tạo một class khác với `@Tags({@Tag("a"), @Tag("b")})`; dùng `getAnnotationsByType(Tag.class)` để quan sát mảng được giải nén từ container.
7. **Phân biệt kiểu dữ liệu:** Viết `@AccessPolicy` với phần tử `Permission[]` như mục 8 và giải thích vì sao không cần `@Repeatable` trên `Permission`.
8. **Tự thiết kế:** Tạo `@HttpHeader(name = "...", value = "...")` và container `@HttpHeaders` để gắn nhiều header lên cùng phương thức. Chọn target, retention, rồi viết code reflection in mọi header. Nhớ rằng annotation chỉ lưu thông tin; việc thực sự gửi HTTP headers cần logic riêng.

**Điểm cần nhớ:** `@Repeatable(Container.class)` cho phép áp dụng **một loại annotation nhiều lần trên cùng phần tử**, còn container phải là **annotation type có `value()` trả về mảng annotation được lặp**, với retention, target và các meta-annotation tương thích. Khi đọc nhiều annotation cùng loại bằng reflection, ưu tiên API **`getAnnotationsByType`** hoặc **`getDeclaredAnnotationsByType`**.
