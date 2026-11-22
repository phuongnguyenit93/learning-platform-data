# Annotation chứa và thuộc tính value trong repeatable annotations (Java)

Trong Java, annotation có thể mô tả một khai báo lớp, phương thức, trường, tham số hoặc những vị trí mà `@Target` cho phép. Thông thường, không thể đặt **nhiều annotation cùng một kiểu** trên cùng một vị trí. Từ **Java 8**, `@Repeatable` cho phép làm điều đó khi kiểu annotation được khai báo đúng và có một **annotation chứa** (*containing annotation type* hay *container annotation*).

Bài này tập trung vào hai thành phần không thể thiếu:

1. **Annotation chứa** là kiểu annotation dùng để gom các instance của annotation lặp. Ví dụ `@Roles` chứa các annotation `@Role`.
2. **Thuộc tính `value()` của annotation chứa** phải trả về **mảng đúng kiểu annotation lặp**, ví dụ `Role[] value();`, chứ không phải `String[]`, `Object[]` hoặc một `List<Role>`.

Mối liên hệ này được khai báo bằng `@Repeatable(ContainerType.class)` ngay trên **annotation được lặp**.

Ví dụ ngắn:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("writer")
class AccountService {
}
```

Hai dòng `@Role(...)` có thể xuất hiện cùng nhau vì `Role` đã chỉ định `Roles` làm container. Khi cần biểu diễn nhiều `@Role` trên cùng phần tử, compiler dùng dạng tương đương về mặt cấu trúc với một `@Roles` chứa mảng các `@Role` theo thứ tự xuất hiện. Cơ chế này vẫn có trong Java hiện đại; không phải tính năng legacy.

**Nhớ ba câu:**

- `@Repeatable(Roles.class)` nằm trên `Role` — **kiểu được phép lặp**.
- `Roles.value()` bắt buộc trả `Role[]` — **các annotation con**.
- Muốn lấy từng `Role` qua reflection, ưu tiên `getAnnotationsByType(Role.class)` hoặc `getDeclaredAnnotationsByType(Role.class)`, không mặc định `getAnnotation(Role.class)` sẽ tự mở container.

## 1. Phân biệt annotation lặp, container và một lần sử dụng annotation

Có ba thực thể dễ nhầm:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Kiểu annotation lặp (*repeatable annotation type*) | `@interface Role` | Định nghĩa loại metadata có thể xuất hiện nhiều lần |
| Kiểu annotation chứa (*containing annotation type*) | `@interface Roles` | Định nghĩa nơi chứa các `Role` trong `value()` |
| Một lần sử dụng annotation (*annotation instance / annotation use*) | `@Role("reader")` | Một giá trị metadata cụ thể gắn ở nơi được phép |

Có thể trực quan hóa:

```text
@Role("reader")
@Role("writer")
class AccountService { }

Biểu diễn logic của container khi có nhiều lần lặp:
@Roles({
    @Role("reader"),
    @Role("writer")
})
class AccountService { }
```

Đây là hình minh họa cấu trúc, không phải việc một lớp luôn đồng thời giữ hai kiểu khai báo nguồn ở đúng một vị trí. Trong cùng một vị trí, **không viết đồng thời cả các `@Role` lặp lẫn `@Roles` tường minh**, vì JLS giới hạn việc trộn annotation lặp với container trên cùng ngữ cảnh.

### 1.1. `@Repeatable` là annotation chuẩn

`@Repeatable` thuộc package:

```java
java.lang.annotation.Repeatable
```

Nó nhận **class token** của kiểu annotation chứa:

```java
@Repeatable(Roles.class)
@interface Role {
    String value();
}
```

`Roles.class` là tham chiếu kiểu container, **không** phải một instance `@Roles`, và không phải tên chuỗi `"Roles"`. Bạn có thể khai báo `Roles` trước hoặc sau `Role` trong mã nguồn phù hợp; compiler giải quyết tham chiếu theo quy tắc Java.

### 1.2. Mỗi kiểu repeatable chỉ chọn một container trực tiếp

Một annotation type được khai báo `@Repeatable(Container.class)` chỉ chỉ định **một kiểu container** cho cơ chế lặp của chính nó. Không thể tạo hai lựa chọn thay thế tùy nơi dùng như `@Repeatable(Roles.class)` và `@Repeatable(OtherRoles.class)` trên cùng kiểu `Role`.

Một container có thể có metadata riêng, nhưng **không nên nhầm** việc container có thêm phần tử với việc có hai cách đóng gói lặp mà compiler tự chọn.

## 2. `value()` là hợp đồng bắt buộc của annotation chứa

Xét:

```java
@interface Roles {
    Role[] value();
}
```

Tại đây, `value` là **tên element/method bắt buộc** theo hợp đồng chứa repeatable annotation. Kiểu trả về phải **chính xác là `Role[]`** nếu `Roles` được khai báo làm container cho `Role`.

| Khai báo `value()` trong `Roles` | Có được dùng làm container của `Role`? | Vì sao |
| --- | --- | --- |
| `Role[] value();` | Có, nếu các quy tắc khác đều đúng | Đúng mảng annotation lặp |
| `String[] value();` | Không | Mảng String, không phải `Role[]` |
| `Object[] value();` | Không | Kiểu phần tử sai, dù mọi annotation đều là object |
| `Role value();` | Không | Chỉ một `Role`, thiếu mảng |
| `List<Role> value();` | Không | Annotation element cũng không cho phép kiểu `List` ở đây |
| `Role[][] value();` | Không | Mảng hai chiều không phải `Role[]` |
| `Role[] roles();` mà không có `value()` | Không | Thiếu tên element bắt buộc `value` |

Những dòng trong bảng là **mẫu chữ ký**, không phải các định nghĩa có thể chép tất cả vào cùng một interface. Hãy kiểm tra cả **tên** và **kiểu trả về**.

### 2.1. Vì sao thuộc tính tên `value` quan trọng?

Trong Java annotation, element có tên `value` cho phép **cú pháp ngắn** khi đó là element duy nhất cần điền:

```java
@Role("reader")
```

tương đương với:

```java
@Role(value = "reader")
```

Tương tự, khi khai báo container một cách tường minh:

```java
@Roles({@Role("reader"), @Role("writer")})
```

tương đương:

```java
@Roles(value = {@Role("reader"), @Role("writer")})
```

**Nhưng cần phân biệt hai `value()`:**

- `Role.value()` là dữ liệu của **mỗi Role**, ở ví dụ này trả `String`.
- `Roles.value()` là **mảng `Role[]`**, bắt buộc để `Roles` là container.

Không có yêu cầu `Role` cũng phải có element `value()`; annotation lặp hoàn toàn có thể dùng `String name()`, `int priority()`, v.v. Yêu cầu cố định về mảng `value()` thuộc **kiểu container**.

### 2.2. Khai báo container có các element bổ sung

Container **được phép có các element ngoài `value()`**, nhưng **mọi element bổ sung phải có default value** nếu container được dùng cho `@Repeatable`:

```java
@interface Roles {
    Role[] value();
    String origin() default "declaration";
    boolean audited() default false;
}
```

Đây là container hợp lệ nếu các điều kiện khác cũng đúng. Vì compiler phải có khả năng tạo container ngầm từ nhiều `@Role`, các element bổ sung phải có giá trị mặc định; nếu không, container ngầm sẽ không thể điền đủ các giá trị yêu cầu.

Khi bạn muốn cấu hình thêm metadata của container một cách tường minh:

```java
@Roles(
    value = {@Role("reader"), @Role("writer")},
    origin = "manual",
    audited = true
)
class ExplicitService {
}
```

Các giá trị `origin` và `audited` áp dụng cho **container**, không tự được sao chép thành element trên từng `Role`. Khi dùng lặp `@Role` ngắn gọn, container ngầm lấy giá trị mặc định của những element phụ này.

## 3. Tại sao container phải được định nghĩa đúng?

Khi compiler gặp:

```java
@Role("reader")
@Role("writer")
class AccountService {}
```

nó cần có cách chuẩn hóa biểu diễn các annotation cùng kiểu. Theo JLS về multiple annotations, nhiều `@Role` cùng một ngữ cảnh có thể được xem như một annotation chứa ngầm, với `value` bao gồm các annotation lặp **theo thứ tự từ trái sang phải** như đã xuất hiện trong source.

Điều này mang lại ba lợi ích:

1. **Tính tương thích cấu trúc metadata:** nhiều repeatable annotations được đóng gói trong container rõ kiểu.
2. **Suy luận nhất quán:** compiler biết chính xác annotation type nào tạo thành array.
3. **Reflection thuận tiện:** Java 8 cung cấp API để đọc các annotations lặp trực tiếp/gián tiếp mà không cần người dùng tự mở container trong trường hợp thường gặp.

Hệ thống annotation từ trước Java 8 đã có những dự án dùng mô hình “container thủ công” theo dạng `@Roles({@Role(...), ...})`. Java 8 bổ sung `@Repeatable` để người dùng có thể viết `@Role` nhiều lần một cách tự nhiên, trong khi vẫn duy trì kiểu container làm một phần hợp đồng. Khi viết mã hiện đại, **không bắt buộc ép người dùng luôn ghi container tường minh**.

## 4. Ví dụ đầy đủ: khai báo `@Repeatable` và container nhất quán

Đây là bộ khai báo điển hình khi ứng dụng cần đọc metadata lúc chạy:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
    int level() default 1;
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
    String source() default "implicit";
}
```

Hai kiểu `Tag` và `Tags` có mối quan hệ:

```text
Tag:
  @Repeatable(Tags.class)
  value(): String
  level(): int = 1

Tags:
  value(): Tag[]             [bắt buộc]
  source(): String = implicit [element phụ có default]
```

`@Retention(RUNTIME)`, `@Target`, `@Documented` và `@Inherited` được viết đồng bộ trên cả hai kiểu để đáp ứng quy tắc của JLS và mục tiêu đọc runtime. Không phải mọi bài toán đều cần `@Inherited` hoặc `@Documented`; ở đây chúng được dùng để minh họa các ràng buộc và ý nghĩa cụ thể.

### 4.1. Chỉ dùng hai annotation lặp, không phải `@Tags` tường minh

```java
@Tag("stable")
@Tag(value = "audited", level = 2)
class OrderHandler {
}
```

Đây là cú pháp được `@Repeatable` mở khóa. Compiler có thể biểu diễn cùng hai tag dưới container với `value` là hai `Tag` theo thứ tự trên.

### 4.2. Dùng container tường minh khi có lý do

```java
@Tags(
    value = {
        @Tag("stable"),
        @Tag(value = "audited", level = 2)
    },
    source = "configuration"
)
class ConfiguredHandler {
}
```

Cú pháp trên có lý khi bạn thật sự cần set thêm element cấp container `source`. Nếu chỉ muốn hai `Tag` và không cần thuộc tính phụ, cách viết lặp ngắn gọn thường dễ đọc hơn.

### 4.3. Một annotation đơn lẻ không bắt buộc tạo container ngầm

Khi có một `@Tag`:

```java
@Tag("single")
class SingleTag {
}
```

Trong trường hợp này, annotation `Tag` có thể **directly present** trên khai báo; không nhất thiết có `@Tags` bao quanh. Điều đó ảnh hưởng đến cách bạn truy vấn bằng reflection:

- `SingleTag.class.getAnnotation(Tag.class)` có thể trả về `Tag` trực tiếp.
- `SingleTag.class.getAnnotation(Tags.class)` thường trả về `null` nếu không có container được khai báo.
- `SingleTag.class.getAnnotationsByType(Tag.class)` trả một phần tử.

Với nhiều `@Tag` ở cùng vị trí, container ngầm thường xuất hiện; khi đó `getAnnotation(Tag.class)` không phải API đáng tin để lấy đủ danh sách.

## 5. Các ràng buộc bắt buộc của annotation chứa theo JLS

Để `@Repeatable(Tags.class)` hợp lệ, kiểu `Tags` phải là một *containing annotation type* thực sự của `Tag`. JLS đặt ra các điều kiện rõ ràng, không chỉ kiểm tra `value()`.

### 5.1. Quy tắc 1 — `value()` phải trả mảng đúng kiểu

```java
@interface Tags {
    Tag[] value();
}
```

Nếu viết `String[] value()`, `Object[] value()` hay `Tag value()`, compiler từ chối khai báo `@Repeatable(Tags.class)`. Không thể bỏ qua kiểm tra này bằng cách cast.

### 5.2. Quy tắc 2 — Các element khác phải có giá trị mặc định

Hợp lệ:

```java
@interface Tags {
    Tag[] value();
    String note() default "";
}
```

Không hợp lệ để làm container cho `Tag`:

```java
@interface Tags {
    Tag[] value();
    String note(); // KHÔNG có default.
}
```

Ở ví dụ lỗi, việc tạo container ngầm từ nhiều `@Tag` không có giá trị bắt buộc cho `note`, nên compiler không thể đáp ứng hợp đồng. Các đoạn trong mục 5 là **các biến thể độc lập để phân tích**, không khai báo lặp tên `Tags` cùng một file.

### 5.3. Quy tắc 3 — Retention của container không được ngắn hơn annotation lặp

`@Retention` chọn annotation tồn tại đến giai đoạn nào:

| Policy | Ý nghĩa |
| --- | --- |
| `SOURCE` | Chỉ tồn tại ở mức nguồn |
| `CLASS` | Lưu trong class file, không yêu cầu phản chiếu runtime thông thường |
| `RUNTIME` | Có thể đọc bằng reflection khi được ghi ở vị trí được hỗ trợ |

Theo JLS, **container phải được giữ ít nhất lâu bằng annotation lặp**:

- Nếu `Tag` có `RUNTIME`, `Tags` cũng phải có `RUNTIME`.
- Nếu `Tag` có `CLASS`, `Tags` có thể là `CLASS` hoặc `RUNTIME`.
- Nếu `Tag` có `SOURCE`, container có thể có retention không ngắn hơn `SOURCE`.
- Nếu không có `@Retention`, mặc định là `CLASS`; đừng giả định đang ở `RUNTIME`.

Một kiểu annotation `RUNTIME` nhưng container chỉ `CLASS` sẽ bị compiler từ chối như một cặp `@Repeatable` không hợp lệ.

**Thiết kế đơn giản nhất:** khi cần reflection runtime, đặt cùng `@Retention(RUNTIME)` trên cả annotation lặp và container.

### 5.4. Quy tắc 4 — `@Target` phải tương thích

`@Target` giới hạn annotation có thể áp dụng lên loại chương trình nào.

Ví dụ minh bạch, dễ bảo trì:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}
```

Với các annotation cho lớp/phương thức, giữ `@Target` nhất quán như ví dụ trên sẽ giúp tránh nhiều lỗi và khó hiểu. Quy tắc chính xác của JLS cho container có những trường hợp đặc biệt liên quan `TYPE`/`TYPE_USE`, `TYPE_PARAMETER`/`TYPE_USE`, cũng như `ANNOTATION_TYPE` và một số ngữ cảnh declaration khác. Vì vậy **không diễn đạt cứng** rằng hai tập `@Target` luôn phải giống hệt nhau; yêu cầu là chúng **tương thích theo JLS**, và những vị trí lặp thực tế phải hợp lệ cho cả base annotation và container ngầm.

Nếu bạn muốn lặp trên field, thêm `ElementType.FIELD` một cách hợp lệ ở cả hai. Nếu muốn lặp trên type-use, xem `TYPE_USE` và các quy tắc type annotations; không tự suy luận một annotation dành riêng cho method sẽ lặp được trên mọi type-use.

### 5.5. Quy tắc 5 — `@Documented` cần được truyền sang container

Nếu annotation lặp `Tag` được khai báo `@Documented`, container `Tags` **cũng phải** được khai báo `@Documented`.

`@Documented` có vai trò hỗ trợ công cụ tạo tài liệu như Javadoc. Nó không khiến annotation tự được phản chiếu khi chạy. Chiều ngược lại được cho phép: một container có thể `@Documented` ngay cả khi base annotation không có annotation đó.

### 5.6. Quy tắc 6 — `@Inherited` cần được truyền sang container

Nếu annotation lặp `Tag` được khai báo `@Inherited`, container `Tags` **cũng phải** có `@Inherited`.

`@Inherited` có tác dụng trong phạm vi kế thừa annotation **trên lớp**, không phải cơ chế tổng quát cho method, field, interface hoặc type-use annotation. Một container có thể `@Inherited` ngay cả khi base annotation không có, nhưng đó thường là cấu hình khó hiểu khi sử dụng reflection; với nhu cầu kế thừa tag rõ ràng, chọn metadata nhất quán.

### 5.7. Ghi nhớ các điều kiện

| Điều kiện trên container | Yêu cầu |
| --- | --- |
| `value()` | Đúng mảng `Tag[]` |
| Các element khác | Bắt buộc có default |
| Retention | Không ngắn hơn `Tag` |
| Target | Tương thích theo luật `@Target` |
| `@Documented` | Bắt buộc có nếu `Tag` có |
| `@Inherited` | Bắt buộc có nếu `Tag` có |

Một container chỉ có `value()` đúng kiểu **chưa bảo đảm** bộ khai báo `@Repeatable` hợp lệ nếu vi phạm các điều kiện còn lại.

## 6. Compiler xử lý nhiều annotation cùng kiểu thế nào?

Với annotation lặp:

```java
@Tag("first")
@Tag("second")
@Tag("third")
class MultiTagged {}
```

Khi các quy tắc về repeatable và vị trí áp dụng được thỏa mãn, compiler tạo một annotation container ngầm về mặt biểu diễn metadata, có nội dung tương ứng:

```java
@Tags({
    @Tag("first"),
    @Tag("second"),
    @Tag("third")
})
class MultiTagged {}
```

**Thứ tự mảng** `value()` là thứ tự các lần lặp ở nguồn, từ trái sang phải. Đây là chi tiết hữu ích khi ứng dụng xem các tag như metadata có trình tự. Tuy vậy, với ý nghĩa như permission hoặc feature flag, bạn nên xác định trong hợp đồng liệu thứ tự có quan trọng hay không, không vô tình dựa vào thứ tự để tạo chính sách không rõ ràng.

### 6.1. Container được sinh khi lặp từ hai lần trở lên

Đối với một lần `@Tag`, thường có annotation trực tiếp `Tag` thay vì một container ngầm `Tags`. Đối với nhiều `@Tag` cùng một vị trí, annotation được biểu diễn **gián tiếp thông qua container** cho các API không tự mở container.

Điều này lý giải vì sao hai kiểu truy vấn có thể cho kết quả khác nhau:

```java
// Với class có hai @Tag trên cùng vị trí:
Tag direct = MultiTagged.class.getAnnotation(Tag.class);
Tag[] all = MultiTagged.class.getAnnotationsByType(Tag.class);
```

`direct` có thể là `null` vì không có `Tag` directly present; `all` có ba phần tử trong ví dụ có ba tag.

### 6.2. Không trộn `@Tag` lặp với `@Tags` trên cùng phần tử

Mã sau cố ý sai khi ở cùng một declaration context:

```java
// KHÔNG BIÊN DỊCH:
// @Tag("one")
// @Tags({@Tag("two"), @Tag("three")})
// class InvalidCombination {}
```

Đây là xung đột giữa một lần dùng annotation lặp và container tường minh trên cùng ngữ cảnh. Hãy chọn một cách: **lặp các `@Tag`** hoặc **dùng một `@Tags` chứa mảng**.

Việc có một annotation lặp duy nhất trong chương trình không bắt buộc viết container bằng tay. Chỉ dùng container tường minh khi bạn cần biểu đạt metadata bổ sung của nó hoặc tương thích với một API cụ thể.

## 7. Reflection: cách đọc `value()` của container

Khi `@Retention(RUNTIME)` được áp dụng đúng, có thể lấy container để đọc mảng:

```java
Tags container =
        MultiTagged.class.getDeclaredAnnotation(Tags.class);

if (container != null) {
    for (Tag tag : container.value()) {
        System.out.println(tag.value());
    }
}
```

Ở ví dụ `MultiTagged` có nhiều `@Tag`, compiler có thể đưa container ngầm vào metadata. `container.value()` trả về mảng `Tag[]`; `tag.value()` bên trong lại trả `String`. Hai lời gọi có cùng tên `value()` nhưng là **hai tầng dữ liệu** khác nhau.

### 7.1. Cần đọc một hay nhiều annotation?

`getAnnotation(Tag.class)` và `getDeclaredAnnotation(Tag.class)` tìm **một annotation trực tiếp/hiện diện theo các quy tắc tương ứng**. Với annotation lặp được đóng trong container, chúng **không phải lựa chọn mặc định để lấy toàn bộ danh sách**.

API Java 8 nên dùng là:

```java
Tag[] tags = MultiTagged.class.getAnnotationsByType(Tag.class);
```

Khi muốn **chỉ annotation được khai báo tại chính phần tử** và không xét inheritance của lớp:

```java
Tag[] tags =
        MultiTagged.class.getDeclaredAnnotationsByType(Tag.class);
```

Hai phương thức có hậu tố `ByType` hiểu kiểu annotation lặp và có thể **nhìn xuyên qua container** để trả các instance bên trong mà bạn không cần gọi `container.value()` thủ công.

### 7.2. Phân biệt các API reflection

| API | Có tự mở container của `@Repeatable`? | Có thể liên quan inheritance của class? |
| --- | --- | --- |
| `getAnnotation(Tag.class)` | Không; tìm một `Tag` theo nghĩa trực tiếp/hiện diện | Có, theo `@Inherited` khi áp dụng |
| `getDeclaredAnnotation(Tag.class)` | Không | Không |
| `getAnnotationsByType(Tag.class)` | **Có** | Có, khi `@Inherited` và các quy tắc associated annotations cho phép |
| `getDeclaredAnnotationsByType(Tag.class)` | **Có** | Không |
| `getAnnotation(Tags.class)` | Trả chính container nếu present, không tự chuyển thành `Tag[]` | Có, tùy `@Inherited` của container |
| `getDeclaredAnnotation(Tags.class)` | Trả trực tiếp container nếu có | Không |

**Gợi ý:** code xử lý các annotation lặp nên thường bắt đầu bằng `getAnnotationsByType(Tag.class)` hoặc `getDeclaredAnnotationsByType(Tag.class)`. Code cần metadata riêng của container, chẳng hạn `source()`, mới truy vấn `Tags.class` và gọi `value()`/`source()`.

### 7.3. `getAnnotations()` có thể khiến bạn bất ngờ

`Class.getDeclaredAnnotations()` hoặc `getAnnotations()` trả các annotation ở mức khai báo theo mô hình “directly present / present”. Với nhiều `@Tag` được đóng gói, bạn có thể gặp **một annotation `Tags`** thay vì nhiều đối tượng `Tag` riêng biệt.

Vì vậy, không nên lặp qua `getDeclaredAnnotations()` rồi lọc `instanceof Tag` để thu thập đầy đủ repeatable annotations. API `ByType` được thiết kế chính cho tình huống đó.

### 7.4. Không lẫn declaration annotation với type-use annotation

Nếu một annotation lặp có `@Target(TYPE_USE)` và được gắn lên **kiểu sử dụng**, vị trí reflection thích hợp có thể là `AnnotatedType`, ví dụ `Field.getAnnotatedType()` hoặc `Method.getAnnotatedReturnType()`, thay vì chỉ tìm declaration annotations trên `Field`/`Method`.

Cách truy vấn phải phản ánh **vị trí thực sự được annotation**. Chữ ký `getAnnotationsByType` có thể có trên các đối tượng hỗ trợ `AnnotatedElement`, nhưng không vì thế mà mọi type-use annotation tự nằm ở lớp/field declaration. Không coi annotation lặp và vị trí gắn annotation là cùng một khái niệm.

## 8. `@Inherited` và repeatable annotations: inherited và local có khác nhau

`@Inherited` chỉ có ý nghĩa cho annotation gắn trên **class declaration** theo cách Java định nghĩa; nó không tự thừa kế annotation trên các method override.

Ví dụ:

```java
@Tag("base-a")
@Tag("base-b")
class BaseHandler {}

class SubHandler extends BaseHandler {}
```

Nếu cả `Tag` và `Tags` được khai báo `@Inherited`, thì:

```java
Tag[] inherited =
        SubHandler.class.getAnnotationsByType(Tag.class);
// Hai phần tử được associated từ BaseHandler theo quy tắc @Inherited.
```

Nhưng:

```java
@Tag("local")
class CustomHandler extends BaseHandler {}
```

thì `CustomHandler.class.getAnnotationsByType(Tag.class)` trả annotation **local**. Nó không tự nối hai tag của superclass vào cuối danh sách. Đây là quy tắc quan trọng: **annotation có mặt ở lớp con không đồng nghĩa danh sách được cộng dồn theo class hierarchy**.

Nếu nghiệp vụ thật sự cần hợp nhất tag từ nhiều mức kế thừa, phải viết rõ chính sách traversal và merge trong code, thay vì tin rằng `getAnnotationsByType` tự gom mọi lớp cha.

### 8.1. `@Inherited` không hoạt động như override method

Lớp con có thể kế thừa metadata class theo chính sách `@Inherited`. Điều này **không có nghĩa** annotation ở method trong superclass sẽ tự xuất hiện trên method override của subclass. Reflection trên method cụ thể xem metadata theo declaration mà bạn truy vấn.

### 8.2. Container và inherited metadata cần khai báo nhất quán

Nếu muốn repeatable annotation `Tag` có hành vi kế thừa, JLS yêu cầu container `Tags` cũng có `@Inherited`. Hai metadata phải phù hợp ngay **khi khai báo annotation type**; không thể “bật” kế thừa ở caller bằng cách cast hoặc sửa truy vấn reflection.

## 9. Chương trình Java hoàn chỉnh: lặp, container và `value()`

Tạo tệp **`RepeatableContainerDemo.java`**. Chương trình biên dịch được trên JDK 17+ và chỉ dùng cú pháp/API hỗ trợ từ Java 8. Nó kiểm tra:

1. Hai annotation `@Tag` lặp trên một class.
2. Container ngầm và mảng `Tag[] value()`.
3. Một `@Tag` duy nhất, không có container ngầm.
4. Container được khai báo tường minh với element bổ sung `source`.
5. `@Inherited` ở class, khác với khai báo tag local trên subclass.
6. Nhiều annotation trên method được đọc bằng `getDeclaredAnnotationsByType`.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

public class RepeatableContainerDemo {

    @Documented
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Repeatable(Tags.class)
    public @interface Tag {
        String value();
        int level() default 1;
    }

    @Documented
    @Inherited
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    public @interface Tags {
        Tag[] value();
        String source() default "implicit";
    }

    @Tag("api")
    @Tag(value = "stable", level = 2)
    static class Service {
    }

    @Tag("only")
    static class Single {
    }

    @Tags(
        value = {@Tag("manual-a"), @Tag("manual-b")},
        source = "manual"
    )
    static class Explicit {
    }

    @Tag("base-a")
    @Tag("base-b")
    static class Base {
    }

    static class Child extends Base {
    }

    @Tag("local")
    static class LocalChild extends Base {
    }

    @Tag("audit")
    @Tag("billing")
    public static void execute() {
    }

    public static void main(String[] args) throws Exception {
        Tag[] serviceTags =
                Service.class.getAnnotationsByType(Tag.class);

        System.out.println("Service count: " + serviceTags.length);
        for (Tag tag : serviceTags) {
            System.out.println("Service tag: "
                    + tag.value() + "/" + tag.level());
        }

        Tags rawContainer =
                Service.class.getDeclaredAnnotation(Tags.class);
        System.out.println("Raw container count: "
                + rawContainer.value().length);
        System.out.println("Raw container source: "
                + rawContainer.source());

        System.out.println("Service direct Tag: "
                + (Service.class.getDeclaredAnnotation(Tag.class)
                        != null));

        System.out.println("Single direct Tag: "
                + (Single.class.getDeclaredAnnotation(Tag.class)
                        != null));
        System.out.println("Single direct container: "
                + (Single.class.getDeclaredAnnotation(Tags.class)
                        != null));

        Tags explicitContainer =
                Explicit.class.getDeclaredAnnotation(Tags.class);
        System.out.println("Explicit count: "
                + Explicit.class.getAnnotationsByType(Tag.class).length);
        System.out.println("Explicit source: "
                + explicitContainer.source());

        System.out.println("Inherited count: "
                + Child.class.getAnnotationsByType(Tag.class).length);
        System.out.println("Local child count: "
                + LocalChild.class.getAnnotationsByType(Tag.class).length);

        Method method = RepeatableContainerDemo.class
                .getDeclaredMethod("execute");
        System.out.println("Method count: "
                + method.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("Method direct Tag: "
                + (method.getDeclaredAnnotation(Tag.class) != null));
    }
}
```

Biên dịch và chạy:

```bash
javac RepeatableContainerDemo.java
java RepeatableContainerDemo
```

**Stdout dự kiến chính xác:**

```text
Service count: 2
Service tag: api/1
Service tag: stable/2
Raw container count: 2
Raw container source: implicit
Service direct Tag: false
Single direct Tag: true
Single direct container: false
Explicit count: 2
Explicit source: manual
Inherited count: 2
Local child count: 1
Method count: 2
Method direct Tag: false
```

Giải thích stdout:

- `Service` có hai `@Tag`, nên `getAnnotationsByType` trả 2 và giữ thứ tự nguồn `api` trước `stable`. `level` mặc định là 1 ở tag thứ nhất, được ghi tường minh là 2 ở tag thứ hai.
- `getDeclaredAnnotation(Tags.class)` trên `Service` nhận được container ngầm; `value().length` bằng 2, còn `source()` lấy default `"implicit"` do không có cấu hình khác.
- `Service.class.getDeclaredAnnotation(Tag.class)` không tìm ra một `Tag` trực tiếp vì hai `Tag` được biểu diễn gián tiếp qua container. Trái lại, `Single` chỉ có một `@Tag` nên truy vấn trực tiếp thành công và không có `Tags` ngầm.
- `Explicit` khai báo một `@Tags` chứa hai `Tag` và đặt `source="manual"`. Reflection bằng `getAnnotationsByType(Tag.class)` vẫn trả đủ hai annotation bên trong.
- `Child` kế thừa hai annotation từ `Base` khi dùng `@Inherited` theo quy tắc class annotation. `LocalChild` có một `@Tag` local, nên `getAnnotationsByType` không tự hợp nhất thêm hai annotation của `Base`.
- `execute` có hai `@Tag` gắn trên method. `getDeclaredAnnotationsByType` trả 2, còn `getDeclaredAnnotation(Tag.class)` không tự mở container nên là null.

Chương trình không phụ thuộc thứ tự reflection trả nhiều **loại annotation không liên quan**; nó chỉ đọc các annotation cùng repeatable type theo thứ tự mà JLS xác định cho container.

## 10. Các lỗi biên dịch phổ biến và cách sửa

### 10.1. Container có `value()` sai kiểu

Sai:

```java
@Repeatable(Roles.class)
@interface Role {
    String name();
}

@interface Roles {
    String[] value(); // SAI: phải là Role[].
}
```

Đây là đoạn **cố ý không biên dịch**. Sửa:

```java
@interface Roles {
    Role[] value();
}
```

### 10.2. Container thiếu `value()`

Sai:

```java
@Repeatable(Roles.class)
@interface Role {
    String name();
}

@interface Roles {
    Role[] entries(); // SAI: tên phải là value().
}
```

Dù `entries()` trả đúng mảng `Role[]`, nó không thỏa yêu cầu **tên element** của container. Phải đổi thành `Role[] value();`.

### 10.3. Element phụ của container không có default

Sai:

```java
@Repeatable(Roles.class)
@interface Role {
    String name();
}

@interface Roles {
    Role[] value();
    String owner(); // SAI: không có default.
}
```

Sửa thành `String owner() default "";` hoặc bỏ `owner` nếu không cần. Điều này cho phép compiler tạo container ngầm khi lặp `@Role`.

### 10.4. Annotation base là RUNTIME, container chỉ CLASS

Sai về retention:

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Roles.class)
@interface Role {
}

@Retention(RetentionPolicy.CLASS)
@interface Roles {
    Role[] value();
}
```

Java từ chối cấu hình container có retention ngắn hơn repeatable annotation. Để đọc bằng reflection, chọn `RUNTIME` cho cả hai.

### 10.5. Base có `@Inherited`, container không có

```java
@Inherited
@Repeatable(Roles.class)
@interface Role {
}

@interface Roles {
    Role[] value();
}
```

Đây là một cấu hình không hợp lệ để `Roles` làm container của `Role`. Khi `Role` khai báo `@Inherited`, `Roles` cũng phải có `@Inherited`.

### 10.6. Base có `@Documented`, container không có

```java
@Documented
@Repeatable(Roles.class)
@interface Role {
}

@interface Roles {
    Role[] value();
}
```

Nếu `Role` có `@Documented`, `Roles` phải được đánh dấu `@Documented`. Lỗi này liên quan đến quy tắc khai báo annotation types, không phải do Javadoc command bị thiếu.

### 10.7. `@Target` không phù hợp giữa base và container

Nếu `Role` có thể lặp trên `ElementType.METHOD` nhưng `Roles` chỉ được phép trên một loại declaration không tương thích, nhiều lần `@Role` trên method không thể được biểu diễn hợp lệ. Cần đối chiếu quy tắc của JLS và chọn container có mục tiêu tương thích.

Giải pháp thông thường: đặt cùng `@Target({ElementType.TYPE, ElementType.METHOD})` trên cả `Role` và `Roles` nếu đây đúng là các vị trí nghiệp vụ cần hỗ trợ.

### 10.8. Trộn annotation base lặp và container cùng vị trí

Sai:

```java
// KHÔNG BIÊN DỊCH:
// @Role(name = "reader")
// @Roles({@Role(name = "writer")})
// class Mixed {}
```

Chọn chỉ `@Role` nhiều lần hoặc chỉ một `@Roles` tường minh. Không cố “bổ sung phần còn thiếu” bằng cách trộn hai kiểu biểu diễn cùng lúc ở một declaration context.

### 10.9. Dùng `getAnnotation(Role.class)` để lấy mọi Role

`getAnnotation` không tự bung các phần tử được chứa gián tiếp khi có nhiều `@Role`. Khi ứng dụng cần tất cả, phải dùng `getAnnotationsByType(Role.class)` hoặc đọc trực tiếp `Roles.value()` nếu có lý do cần thao tác container.

### 10.10. Tưởng `@Repeatable` thay thế `@Retention`

`@Repeatable` chỉ mở cơ chế lặp, không buộc metadata được giữ lại đến runtime. Nếu cần reflection, vẫn phải dùng `@Retention(RUNTIME)` và đảm bảo container có retention không ngắn hơn. Nếu thiếu retention, mặc định là `CLASS`.

## 11. Thiết kế API annotation bền vững

### 11.1. Ưu tiên tên số nhiều cho container

Ví dụ:

- `@Role` / `@Roles`.
- `@Tag` / `@Tags`.
- `@Permission` / `@Permissions`.

Tên số nhiều là **quy ước dễ đọc**, không phải ràng buộc của compiler. Compiler chỉ kiểm tra `@Repeatable(Container.class)` và các điều kiện của annotation chứa.

### 11.2. Không dùng container để đánh lừa logic nghiệp vụ

Giả sử annotation `@Permission` mô tả quyền truy cập. Bạn có thể có nhiều annotation, nhưng nên xác định rõ liệu các quyền là:

- Một tập hợp OR (chỉ cần một quyền).
- Một tập hợp AND (phải có tất cả quyền).
- Danh sách ưu tiên, có thứ tự.
- Một bảng quy tắc hợp nhất theo role, tenant hoặc environment.

**`@Repeatable` không đưa ra ngữ nghĩa bảo mật.** Nó chỉ cho phép cú pháp metadata lặp và container hóa. Mọi quyết định xác thực/phân quyền cần code hoặc framework chính sách đã được kiểm thử.

### 11.3. Dùng element phụ của container một cách có chủ đích

Nếu cần `source` hoặc `group` ở cấp container, hãy cân nhắc:

- Những element đó có thật sự có ý nghĩa chung cho tất cả các tag trong mảng không?
- Có default giá trị hợp lý không? JLS **bắt buộc default** cho element phụ.
- Người dùng có cần khai báo container tường minh để đặt element phụ không?
- Nếu thiếu thông tin, có nên dùng dữ liệu trên từng base annotation thay vì container không?

Vì cú pháp các lần lặp `@Tag` không mang theo các tùy chọn container như `source`, thiết kế element phụ nên tránh những trường dữ liệu bắt buộc về mặt nghiệp vụ nhưng bị JLS buộc phải có default ở mức annotation container.

### 11.4. Đừng giả định mọi annotation lặp đều là class declaration annotation

`@Target` quyết định vị trí. Bạn có thể có repeatable annotations dành cho method, field, parameter hoặc type-use. Mỗi vị trí tương ứng với cách truy xuất metadata bằng reflection/compiler khác nhau.

Với type-use annotation lặp trong generics hoặc kiểu của biến, hãy kiểm tra API `AnnotatedType` phù hợp; không tự suy ra `Class.getAnnotationsByType` bao quát mọi nơi mà annotation xuất hiện.

### 11.5. Khi nào cần container tường minh?

Thông thường, caller chỉ cần lặp:

```java
@Tag("first")
@Tag("second")
```

Dùng `@Tags({...})` tường minh khi:

- API hoặc công cụ xử lý đang cần một cấu trúc chứa được cấu hình cụ thể.
- Bạn muốn ghi thêm element phụ của container như `source`.
- Bạn đang tương tác với một thiết kế annotation hiện có đã công bố container như một phần của giao diện cấu hình.

Đừng ép mọi caller viết container thủ công nếu `@Repeatable` đã đáp ứng yêu cầu.

## 12. Checklist trước khi công bố một repeatable annotation

1. Định nghĩa rõ base annotation, ví dụ `@interface Tag`.
2. Chọn tên container, ví dụ `@interface Tags`.
3. Trên base đặt `@Repeatable(Tags.class)`.
4. Trong container có **`Tag[] value();`**, đúng tên và đúng kiểu.
5. Mọi element khác trong container đều có `default`.
6. Chọn retention: nếu cần reflection, cả hai dùng `@Retention(RUNTIME)`.
7. Chọn target tương thích giữa base và container theo JLS; bắt đầu bằng cùng `@Target` nếu phù hợp.
8. Nếu base có `@Documented`, container cũng phải có.
9. Nếu base có `@Inherited`, container cũng phải có; hiểu rõ rằng inheritance chỉ có ý nghĩa thích hợp với lớp.
10. Viết test cho một base annotation, hai base annotations và container tường minh.
11. Test `getAnnotationsByType` và `getDeclaredAnnotationsByType`; tránh chỉ dùng `getAnnotation`.
12. Nếu container có element phụ, test giá trị default và giá trị tường minh của nó.
13. Xác định chính sách nghiệp vụ cho thứ tự, trùng lặp hoặc xung đột metadata.
14. Khi nâng cấp annotation đã public, kiểm thử compatibility với các class/library cũ và người dùng reflection.
15. Dùng công cụ/compiler JDK được hỗ trợ thực tế, không dựa vào cú pháp annotation riêng của framework nếu muốn đây là hợp đồng Java thuần.

## 13. Tóm tắt và câu hỏi tự kiểm tra

**Tóm tắt:**

- `@Repeatable(Tags.class)` khai báo `Tag` là repeatable, với `Tags` là annotation chứa.
- `Tags` **bắt buộc** có `Tag[] value();`.
- Mọi element khác của `Tags` đều phải có giá trị mặc định.
- Retention và target phải hợp lệ; `@Documented`/`@Inherited` của base tạo ràng buộc đối với container.
- Nhiều `@Tag` trên cùng vị trí được biểu diễn qua container với mảng `value()` theo thứ tự từ trái sang phải.
- Một `@Tag` duy nhất có thể trực tiếp hiện diện, không có container ngầm.
- `getAnnotationsByType(Tag.class)` giúp lấy tất cả base annotations, kể cả khi nằm trong container.
- `getDeclaredAnnotationsByType(Tag.class)` chỉ đọc theo declaration của chính phần tử, không kế thừa từ superclass.
- `@Inherited` không có nghĩa là cộng dồn mọi annotation từ toàn bộ chuỗi kế thừa.
- Container là cấu trúc metadata, **không tự định nghĩa chính sách nghiệp vụ**.

**Tự kiểm tra:**

1. Vì sao `Role[] value();` phải thuộc container `Roles`, trong khi `Role.value()` có thể là `String`?
2. Nếu `Roles` thêm `String owner();` mà không có `default`, compiler xử lý khai báo `@Repeatable(Roles.class)` thế nào?
3. Vì sao `@Retention(CLASS)` trên container không phù hợp nếu annotation lặp có `RUNTIME`?
4. Khi một class có ba `@Tag`, `getAnnotation(Tag.class)` và `getAnnotationsByType(Tag.class)` khác nhau thế nào?
5. Khi một class chỉ có một `@Tag`, có nhất thiết tồn tại một `@Tags` ngầm không?
6. Nếu `@Tag` có `@Inherited`, container cần meta-annotation nào? Việc này có làm method annotations tự kế thừa không?
7. Nếu bạn muốn thêm `source="manual"` vào container, nên dùng cú pháp lặp hay container tường minh?
8. Khi cần xem repeatable type annotation trên kiểu trả về của method, nên kiểm tra `Method.getAnnotationsByType` hay `Method.getAnnotatedReturnType()`?

## Tài liệu chuẩn

- Java Language Specification (Java SE 25), **`9.6.3 Repeatable Annotation Interfaces**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.3
- Java Language Specification (Java SE 25), **`9.7.5 Multiple Annotations of the Same Interface**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.5
- Java SE API, **`java.lang.annotation.Repeatable`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Repeatable.html
- Java SE API, **`java.lang.reflect.AnnotatedElement`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
