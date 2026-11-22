# Quan hệ Target, Retention, Documented và Inherited trong annotation lặp (Java 8)

## 1. Bản chất của annotation lặp

Từ Java 8, **repeatable annotation** cho phép lặp lại cùng một annotation trên **một vị trí** được Java cho phép. Ví dụ:

```java
@Role("read")
@Role("write")
class AccountService { }
```

Đây là đoạn minh họa, giả sử `Role` được khai báo repeatable và được phép gắn lên class. Điểm quan trọng: Java không đơn thuần cho phép nhiều annotation cùng tên. Một **annotation gốc** (*repeatable annotation type*, ký hiệu A) phải khai báo `@Repeatable(Container.class)`, và **annotation chứa** (*containing annotation type*, ký hiệu AC) phải thỏa các điều kiện của Java Language Specification (JLS).

Bốn meta-annotation cần học trong quan hệ này:

- **`@Target`**: xác định vị trí annotation có thể được sử dụng.
- **`@Retention`**: xác định metadata tồn tại đến source, class file hay runtime.
- **`@Documented`**: xác định chính sách đưa annotation vào tài liệu API (Javadoc).
- **`@Inherited`**: xác định cách annotation trên class có thể được tra cứu từ superclass.

Các quy tắc này được giới thiệu cùng repeatable annotations ở Java 8 và **vẫn áp dụng trong Java hiện đại**. Bài học chỉ dùng kiến thức và API còn được duy trì, không dùng các cơ chế legacy hay lỗi thời.

Sau bài học, bạn sẽ biết định nghĩa cặp base/container hợp lệ, đọc metadata qua reflection, giải thích những tình huống kế thừa và nhận ra các ví dụ compiler phải từ chối.

## 2. Cấu trúc base annotation và container

Ví dụ tối giản:

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

`Tag` là base annotation; `Tags` là container được `@Repeatable` chỉ định. Khi dùng nhiều `@Tag`, Java biểu diễn chúng qua một container chứa mảng Tag theo thứ tự nguồn.

Một container hợp lệ phải:

1. Có phần tử **`value()` trả chính xác mảng annotation gốc**, ở đây là `Tag[]`.
2. Với mọi phần tử **khác `value()`**, nếu có, phải cung cấp **default value** để compiler có thể tạo container ngầm.
3. Có `@Target`, `@Retention`, `@Documented`, `@Inherited` phù hợp theo các điều kiện tương quan mà JLS quy định.

Điểm 1 không thể thay bằng `String[]`, `Object[]` hoặc `List<Tag>`. Dạng `Tag[]` là **cấu trúc bắt buộc**, không chỉ là lựa chọn tiện lợi.

**Lưu ý về retention:** hai annotation vừa khai báo không có `@Retention`, do đó mặc định là `RetentionPolicy.CLASS`. Chúng có thể được compiler chấp nhận nhưng không được Java runtime reflection hứa hẹn truy cập. Muốn kiểm chứng `getAnnotationsByType` lúc chạy, dùng một cặp có `RUNTIME` retention như ví dụ ở mục 9.

## 3. Tóm tắt bốn quan hệ bắt buộc

| Meta-annotation | Trên base A | Trên container AC | Quy tắc |
| --- | --- | --- | --- |
| `@Target` | Nơi A có thể dùng | Nơi AC có thể dùng | A áp dụng được ít nhất tại những loại vị trí mà AC áp dụng được, với ngoại lệ ngữ nghĩa JLS. |
| `@Retention` | Đời sống metadata A | Đời sống metadata AC | AC phải được giữ **ít nhất lâu bằng A**. |
| `@Documented` | Base xuất hiện trong docs | Container xuất hiện trong docs | Nếu A Documented thì AC cũng phải Documented. |
| `@Inherited` | Class annotation có thể kế thừa | Container có thể kế thừa | Nếu A Inherited thì AC cũng phải Inherited. |

Hai dòng cuối là điều kiện **một chiều**: base có ⇒ container phải có. **Container có nhưng base không có vẫn có thể hợp lệ**. Java không đòi cặp annotation lúc nào cũng giống hệt nhau về mọi metadata, nhưng muốn API dễ sử dụng thì thông thường nên giữ nhất quán.

## 4. `@Target`: giới hạn nơi annotation được phép lặp

Java có nhiều `ElementType` như `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `TYPE_USE`, `TYPE_PARAMETER`. `@Target` mô tả nơi annotation được phép áp dụng.

### Container được phép hẹp hơn base

Ví dụ hợp lệ:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Items.class)
@interface Item {
    String value();
}

@Target(ElementType.TYPE)
@interface Items {
    Item[] value();
}
```

Giả sử đã import `Target`, `ElementType`, `Repeatable`. Base `Item` được phép ở **TYPE và METHOD**; container `Items` chỉ được ở **TYPE**. Điều này hợp lệ: **container hẹp hơn base**.

Hệ quả:

- `@Item("a")` đơn lẻ trên một method là hợp lệ.
- `@Item("a") @Item("b")` trên một class là hợp lệ.
- `@Item("a") @Item("b")` trên method **không hợp lệ**, vì compiler cần container ngầm `@Items` tại METHOD nhưng `Items` không cho phép METHOD.

Do đó, đừng nhầm rằng container phải chứa **mọi target** của base. Về nguyên tắc, **nơi muốn lặp phải cho phép cả base lẫn container**.

### Container không được rộng hơn khả năng áp dụng của base

Ví dụ sai, cố ý không biên dịch:

```java
@Target(ElementType.METHOD)
@Repeatable(Events.class)
@interface Event { String value(); }

@Target({ElementType.METHOD, ElementType.FIELD})
@interface Events { Event[] value(); }
```

Container Events cho phép FIELD, nhưng base Event không cho phép FIELD. Đây là một lỗi trong quan hệ target.

### Những trường hợp đặc biệt từ JLS

Quy tắc so sánh target không đơn thuần là tập con của hai mảng enum trong mọi trường hợp. JLS §9.6.3 có những khả năng tương đương:

- AC có `ANNOTATION_TYPE`: A phải có ít nhất một trong `ANNOTATION_TYPE`, `TYPE`, `TYPE_USE`.
- AC có `TYPE`: A phải có ít nhất một trong `TYPE`, `TYPE_USE`.
- AC có `TYPE_PARAMETER`: A phải có ít nhất một trong `TYPE_PARAMETER`, `TYPE_USE`.

Cần hiểu đây là quan hệ về **vị trí mà annotation thực sự có thể áp dụng**. Nếu làm annotation lặp trên type-use/generic, nên viết compile tests cho đúng syntax, không suy luận hoàn toàn từ tên enum.

**Không có `@Target` cũng không có nghĩa tự hỗ trợ mọi `TYPE_USE`**. Annotation không Target có thể áp dụng trong declaration contexts theo JLS nhưng không tự được phép ở mọi type context như `List<@X String>`.

## 5. `@Retention`: vòng đời của base và container

`RetentionPolicy` có ba mức:

```text
SOURCE -> CLASS -> RUNTIME
```

| Base A | Retention AC hợp lệ | Retention AC không hợp lệ |
| --- | --- | --- |
| SOURCE | SOURCE, CLASS, RUNTIME | Không có mức ngắn hơn SOURCE |
| CLASS | CLASS, RUNTIME | SOURCE |
| RUNTIME | RUNTIME | SOURCE, CLASS |

Nguyên tắc là **container không được tồn tại ngắn hơn base**. Khi A xuất hiện nhiều lần, compiler lưu các giá trị lặp thông qua container. Nếu base hứa tồn tại ở RUNTIME mà container chỉ giữ đến CLASS thì client runtime không có mức metadata phù hợp; compiler sẽ từ chối.

Ví dụ hợp lệ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Flags.class)
@interface Flag { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@interface Flags { Flag[] value(); }
```

Ví dụ sai, cố ý không biên dịch:

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Marks.class)
@interface Mark { String value(); }

@Retention(RetentionPolicy.CLASS)
@interface Marks { Mark[] value(); }
```

Base RUNTIME, container CLASS: sai.

Một annotation không có `@Retention` được mặc định **CLASS**, không phải RUNTIME. Nếu hệ thống thực sự đọc bằng Java reflection, nên chọn `RUNTIME` cho cả base và container rồi kiểm thử. Nếu chỉ dùng static analyzer/class-file reader, CLASS hoặc SOURCE có thể thích hợp tùy công cụ.

**Hai điều kiện độc lập:** `@Documented` không tự làm annotation có runtime retention; `@Inherited` cũng không tự đổi mức retention.

## 6. `@Documented`: quan hệ một chiều và Javadoc

`@Documented` chỉ dẫn công cụ tài liệu Java rằng annotation type cần được xem như thông tin xuất hiện trong **tài liệu API** của phần tử được annotate.

Ví dụ hợp lệ:

```java
@Documented
@Repeatable(Notes.class)
@interface Note { String value(); }

@Documented
@interface Notes { Note[] value(); }
```

Khi Note có `@Documented`, container Notes **bắt buộc** có `@Documented`. Ngược lại, nếu Notes có Documented nhưng Note không có, JLS vẫn cho phép.

Ví dụ cố ý không biên dịch:

```java
@Documented
@Repeatable(Notes.class)
@interface Note { String value(); }

@interface Notes { Note[] value(); } // Thiếu @Documented.
```

**Không nhầm `@Documented` với `@Retention(RUNTIME)`.** Documented ảnh hưởng tài liệu Javadoc; Retention ảnh hưởng vòng đời metadata. Nếu muốn chứng minh một annotation được render trong tài liệu, hãy chạy công cụ `javadoc` trên API mẫu. Gọi `Role.class.isAnnotationPresent(Documented.class)` chỉ chứng minh **meta-annotation có trên annotation type**, không phải chứng minh HTML đã được tạo đúng.

## 7. `@Inherited`: chỉ kế thừa annotation class theo quy tắc Java

`@Inherited` cho phép reflection tra cứu annotation của **class con** từ một **superclass** trong những điều kiện được định nghĩa.

Với base A và container AC:

- A có `@Inherited` ⇒ AC **bắt buộc** có `@Inherited`.
- AC có `@Inherited` trong khi A không có ⇒ vẫn có thể hợp lệ, nhưng không được suy ra rằng `getAnnotationsByType(A.class)` sẽ tự kế thừa A.
- `@Inherited` không tự áp dụng qua **interface implementation**.
- `@Inherited` không tự chuyển annotation trên **method ở superclass** sang **method override**.
- `@Inherited` không tự **gộp tất cả annotations** trên mọi cấp superclass.

Giả sử Role/Roles đều `@Inherited`, `RUNTIME`:

```java
@Role("read")
@Role("write")
class Parent { }

class Child extends Parent { }

@Role("local")
class OverrideChild extends Parent { }
```

Với Child không có Role trực tiếp, `Child.class.getAnnotationsByType(Role.class)` có thể trả `read,write` được kế thừa. Nhưng `Child.class.getDeclaredAnnotationsByType(Role.class)` chỉ đọc annotation **trên chính Child**, nên không trả Role từ Parent.

Với OverrideChild có Role trực tiếp, `getAnnotationsByType(Role.class)` trả `local`, **không tự gộp** thành `local,read,write`.

Nếu framework cần kế thừa quyền qua cả superclass, interfaces và method override, đó phải là **policy riêng của framework**. Java `@Inherited` một mình không hứa thực hiện bất kỳ phép gộp nào như vậy.

## 8. Reflection: `getAnnotation` khác `getAnnotationsByType`

Repeatable annotations có thể hiện diện:

- **Directly present**: một annotation A xuất hiện trực tiếp trên phần tử.
- **Indirectly present**: A được chứa trong AC đang có trên phần tử.
- **Associated**: A trực tiếp/gián tiếp, và với class có thể từ superclass nếu A inheritable theo luật reflection.

| Reflection API | Ý nghĩa |
| --- | --- |
| `getAnnotation(A.class)` | Đọc một A present, không tự bung container thành các A. |
| `getDeclaredAnnotation(A.class)` | Đọc A khai báo trực tiếp, không tìm superclass. |
| `getAnnotationsByType(A.class)` | Đọc các A associated, gồm A được chứa và có thể inherited. |
| `getDeclaredAnnotationsByType(A.class)` | Đọc các A trực tiếp/gián tiếp **trên chính phần tử**. |
| `getAnnotation(AC.class)` | Đọc container khi present theo API. |
| `getDeclaredAnnotations()` | Đọc annotations được khai báo trên phần tử; có thể thấy container thay vì mỗi A lặp. |

### Một Role so với hai Role

Nếu class chỉ có `@Role("one")`, `getAnnotation(Role.class)` có thể đọc Role trực tiếp. Nhưng nếu class có `@Role("read") @Role("write")`, compiler biểu diễn qua container `Roles`; `getAnnotation(Role.class)` có thể trả **null** dù có hai Role. Dùng `getAnnotationsByType(Role.class)` để đọc đủ hai giá trị.

Khi compiler tạo container do lặp, các phần tử annotation gốc được giữ theo **thứ tự từ trái qua phải** của source. Nếu bạn dùng thứ tự này cho nghiệp vụ quan trọng, phải có contract rõ về thứ tự xử lý và kiểm thử thực tế.

## 9. Ví dụ Java chạy độc lập

Tạo tệp **`RepeatableMetaDemo.java`**. Chương trình minh họa một cặp Role/Roles có đủ meta-annotations và một cặp Label/Labels không Inherited, rồi kiểm tra hành vi reflection.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

public class RepeatableMetaDemo {
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Inherited
    @Repeatable(Roles.class)
    public @interface Role {
        String value();
    }

    @Target({ElementType.TYPE, ElementType.METHOD})
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Inherited
    public @interface Roles {
        Role[] value();
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Repeatable(Labels.class)
    public @interface Label {
        String value();
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Labels {
        Label[] value();
    }

    @Role("read")
    @Role("write")
    public static class Parent {
        @Role("base-method")
        public void run() { }
    }

    public static class Child extends Parent {
        @Override public void run() { }
    }

    @Role("local")
    public static class OverrideChild extends Parent { }

    @Label("alpha")
    @Label("beta")
    public static class Plain { }

    public static class PlainChild extends Plain { }

    @Role("one")
    public static class Single { }

    private static String roles(Role[] data) {
        return Arrays.stream(data)
                .map(Role::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("parentDirectRole="
                + (Parent.class.getAnnotation(Role.class) != null));
        System.out.println("parentContainer="
                + (Parent.class.getAnnotation(Roles.class) != null));
        System.out.println("parentByType="
                + roles(Parent.class.getAnnotationsByType(Role.class)));
        System.out.println("childByType="
                + roles(Child.class.getAnnotationsByType(Role.class)));
        System.out.println("childDeclared="
                + Child.class.getDeclaredAnnotationsByType(Role.class).length);
        System.out.println("overrideByType="
                + roles(OverrideChild.class.getAnnotationsByType(Role.class)));
        System.out.println("methodOverrideInherited="
                + Child.class.getDeclaredMethod("run")
                    .getAnnotationsByType(Role.class).length);
        System.out.println("plainChildByType="
                + PlainChild.class.getAnnotationsByType(Label.class).length);
        System.out.println("singleDirect="
                + Single.class.getAnnotation(Role.class).value());
        System.out.println("documented="
                + Role.class.isAnnotationPresent(Documented.class)
                + "/" + Roles.class.isAnnotationPresent(Documented.class));
        System.out.println("inherited="
                + Role.class.isAnnotationPresent(Inherited.class)
                + "/" + Roles.class.isAnnotationPresent(Inherited.class));
    }
}
```

Biên dịch và chạy bằng JDK 17+ (chỉ dùng API có từ Java 8):

```bash
javac RepeatableMetaDemo.java
java RepeatableMetaDemo
```

**Stdout chính xác:**

```text
parentDirectRole=false
parentContainer=true
parentByType=read,write
childByType=read,write
childDeclared=0
overrideByType=local
methodOverrideInherited=0
plainChildByType=0
singleDirect=one
documented=true/true
inherited=true/true
```

### Giải thích kết quả từng bước

1. **`parentDirectRole=false`**: hai Role ở Parent được biểu diễn qua container; `getAnnotation(Role.class)` không tự bung container.
2. **`parentContainer=true`**: `getAnnotation(Roles.class)` đọc được container.
3. **`parentByType=read,write`**: `getAnnotationsByType(Role.class)` trả đủ các Role từ container.
4. **`childByType=read,write`**: Child không có Role trực tiếp và Role có `@Inherited`, nên có thể tra Role ở superclass.
5. **`childDeclared=0`**: `getDeclaredAnnotationsByType` không đi superclass.
6. **`overrideByType=local`**: OverrideChild có Role trực tiếp; kết quả không tự gộp Role của Parent.
7. **`methodOverrideInherited=0`**: annotation trên Parent.run không tự chuyển sang Child.run khi override.
8. **`plainChildByType=0`**: Label không có `@Inherited`, nên PlainChild không tự kế thừa Label của Plain.
9. **`singleDirect=one`**: Single có một Role trực tiếp, vì vậy `getAnnotation(Role.class)` đọc được.
10. **`documented=true/true`**: hai annotation types có `@Documented`, không phải phép thử Javadoc output.
11. **`inherited=true/true`**: hai annotation types có `@Inherited`, phù hợp quan hệ JLS.

**Tính an toàn nghiệp vụ:** `@Role("admin")` không tự cấp quyền. Security/framework phải thực sự đọc annotations, đặt policy về quyền kế thừa, thứ tự, merge và thực thi kiểm soát.

## 10. Các lỗi biên dịch điển hình

Những khối code sau **cố ý sai**, chỉ dùng để minh họa lỗi và được giả định có import từ `java.lang.annotation`.

### Container `value()` không đúng kiểu

```java
@Repeatable(BadContainer.class)
@interface Bad { }

@interface BadContainer {
    String[] value(); // Sai: phải là Bad[].
}
```

Phần tử khác `value()` của container phải có **default**, chẳng hạn:

```java
@Repeatable(Groups.class)
@interface Group { String value(); }

@interface Groups {
    Group[] value();
    String owner(); // Sai: thiếu default.
}
```

### Container Retention ngắn hơn

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Marks.class)
@interface Mark { String value(); }

@Retention(RetentionPolicy.CLASS)
@interface Marks { Mark[] value(); }
```

Sai vì base RUNTIME nhưng container chỉ CLASS.

### Container thiếu Documented

```java
@Documented
@Repeatable(Notes.class)
@interface Note { }

@interface Notes { Note[] value(); } // Sai.
```

Nếu base Documented, container cũng phải Documented.

### Container thiếu Inherited

```java
@Inherited
@Repeatable(Tags.class)
@interface Tag { }

@interface Tags { Tag[] value(); } // Sai.
```

Nếu base Inherited, container cũng phải Inherited.

### Container target không tương thích

```java
@Target(ElementType.METHOD)
@Repeatable(Flags.class)
@interface Flag { String value(); }

@Target(ElementType.FIELD)
@interface Flags { Flag[] value(); } // Sai.
```

Container dùng được ở FIELD trong khi base không dùng được ở FIELD.

**Không ghép những ví dụ lỗi này vào chương trình chính**, và không dùng chúng như các mẫu code để triển khai thật.

## 11. Những hiểu nhầm thường gặp ở runtime

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `getAnnotation(Base.class)` luôn đọc được mọi annotation lặp | Nó chỉ trả một annotation present; dùng `getAnnotationsByType` để đọc nhiều giá trị. |
| Có `@Inherited` thì class nhận annotation từ interface | Không; Java inherited annotations là tra cứu trên **superclass**. |
| Có `@Inherited` thì method override kế thừa annotation | Không; framework phải có logic riêng nếu muốn điều đó. |
| `getDeclaredAnnotationsByType` đi lên superclass | Không; chỉ đọc trực tiếp/gián tiếp trên phần tử hiện tại. |
| Subclass có Role riêng sẽ tự cộng Role từ Parent | Không; lookup mặc định không phải phép merge. |
| Chỉ container có `@Inherited` thì base by-type tự được inherited | Không được suy luận như vậy; xét `@Inherited` trên base type được truy vấn. |
| `@Documented` làm annotation đọc được ở runtime | Không; runtime retention là vai trò của `@Retention`. |
| Không có `@Target` là được ở mọi type-use context | Không; type-use cần applicability tương ứng. |
| Container được phép có mọi target của base cộng thêm nhiều target mới | Không; container phải đáp ứng quan hệ target của JLS. |
| Annotation giúp JVM tự enforce validation/permission | Không; annotation là metadata cho compiler/tool/framework sử dụng theo contract. |

### Trộn annotation base và container ở cùng vị trí

Java có quy tắc cấm viết **nhiều base annotation cùng với container của chúng** theo một số cách gây trùng, ví dụ cố lặp `@Role` rồi thêm `@Roles` trực tiếp ở cùng vị trí. Hãy chọn một cách khai báo hợp lệ, không dùng cả hai với suy nghĩ sẽ tăng tính tương thích của reflection.

### Khi nào dùng `getDeclaredAnnotationsByType`?

Dùng khi framework cần **chỉ các annotation công bố bởi chính class hiện tại**, không lấy superclass. Nếu muốn inherited semantics, dùng `getAnnotationsByType` trên class và kiểm tra `@Inherited`/container phù hợp. Với method, field, parameter, interface, cần policy rõ vì cơ chế inherited mặc định không giải quyết toàn bộ hierarchy của ứng dụng.

## 12. Thiết kế thư viện annotation an toàn

Khi phát hành repeatable annotation công khai:

1. **Chọn target vừa đủ**: những declaration/type contexts mà base và container cần áp dụng; viết compile test cho mỗi vị trí.
2. **Chọn retention theo người tiêu thụ**: RUNTIME nếu reflection JVM cần đọc, CLASS/SOURCE nếu chỉ build-time tooling.
3. **Đồng bộ Documented và Inherited** khi base có; giữ metadata nhất quán nếu không có lý do khác biệt.
4. **Đặt tên container rõ ràng**: `Role`/`Roles`, `Rule`/`Rules`; tránh xung đột loại và tên.
5. **Công bố semantics**: annotation dùng cho metadata, validation, routing hay security? Trùng giá trị được cho phép không? Thứ tự có ý nghĩa không?
6. **Kiểm thử reflection**: một Role, nhiều Role, trực tiếp, trong container, class con và class con có Role riêng.
7. **Kiểm thử inheritance thực**: class inheritance khác interface/method override. Nếu cần kết hợp, định nghĩa thuật toán riêng.
8. **Chạy Javadoc** khi `@Documented` là một cam kết của API docs.
9. **Đảm bảo công cụ đọc đúng**: prefer `getAnnotationsByType` với repeatable metadata khi cần mọi giá trị.
10. **Đánh giá tác động khi nâng cấp**: đổi target, retention, documented, inherited hoặc cấu trúc container có thể ảnh hưởng client source, framework và tài liệu.

Những thay đổi metadata có thể không sửa Java method signature nhưng vẫn đổi hành vi ứng dụng. Ví dụ đổi RUNTIME thành CLASS làm framework mất annotations; đổi Inherited có thể thay kết quả trên subclass; đổi Documented ảnh hưởng API docs. Vì vậy cần versioning và tests phù hợp.

## 13. Câu hỏi tự kiểm tra

**1.** Base `@Target({TYPE, METHOD})`, container `@Target(TYPE)` có thể hợp lệ?  
**Có.** Container hẹp hơn base. Nhưng không được lặp base ở METHOD khi container không áp dụng tại METHOD.

**2.** Base RUNTIME, container CLASS hợp lệ không?  
**Không.** Container không được có retention ngắn hơn base.

**3.** Base SOURCE, container RUNTIME có thể thỏa điều kiện retention?  
**Có** nếu các quy tắc khác cũng đúng; không tự bảo đảm mọi cách đọc runtime đều phù hợp mục tiêu.

**4.** Base Documented, container không Documented hợp lệ?  
**Không.** Container bắt buộc Documented.

**5.** Container Documented, base không Documented hợp lệ?  
**Có thể hợp lệ.** Đây là điều kiện một chiều.

**6.** Base Inherited, container không Inherited hợp lệ?  
**Không.** Container phải Inherited.

**7.** Container Inherited, base không Inherited thì `getAnnotationsByType(Base.class)` chắc chắn đọc được base trên subclass?  
**Không.** Không suy diễn base inheritable chỉ từ container.

**8.** Parent có hai Role, `getAnnotation(Role.class)` trả null. Có chắc không có Role?  
**Không.** Dùng `getAnnotationsByType(Role.class)`.

**9.** Child không khai báo Role, Parent có Role inherited. `getDeclaredAnnotationsByType` trên Child có đọc Role Parent?  
**Không.** Chỉ đọc annotation trên Child.

**10.** Child có Role riêng, Parent có hai Role inherited: Java tự gộp thành ba Role?  
**Không.** Annotation trực tiếp trên Child không tự merge với Parent.

**11.** Method Child override method Parent: `@Inherited` tự sao annotation method từ Parent?  
**Không.** Chỉ có inheritance semantics của class theo Java.

**12.** `@Documented` có làm annotation runtime reflection nhìn thấy không?  
**Không.** Cần Retention và API phù hợp.

**13.** Container `value(): String[]` cho base Role hợp lệ?  
**Không.** Bắt buộc trả `Role[]`.

**14.** Container có thêm `String owner();` không default hợp lệ?  
**Không.** Phần tử bổ sung cần giá trị mặc định.

## 14. Tổng kết và tài liệu chính thức

**Repeatable annotation là cặp base/container có quan hệ ràng buộc**. Container cần `value(): Base[]`, có target phù hợp/không rộng hơn khả năng áp dụng của base theo JLS, retention **không ngắn hơn** base; khi base `@Documented` hoặc `@Inherited`, container bắt buộc có meta-annotation tương ứng. Chiều ngược lại của Documented/Inherited không bắt buộc.

**Runtime reflection cần đọc bằng API đúng:** `getAnnotationsByType` trả các annotation lặp, `getDeclaredAnnotationsByType` chỉ nhìn phần tử hiện tại. `@Inherited` không tự đi qua interface/method override và không gộp mọi cấp class. Những quy tắc này vẫn hiện hành trong Java hiện đại.

Tài liệu nguồn chính thức:

- [JLS §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.3).
- [JLS §9.6.4.1 — Target](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.1).
- [JLS §9.6.4.2 — Retention](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2).
- [JLS §9.6.4.3 — Inherited](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.3).
- [JLS §9.7.5 — Multiple Annotations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.5).
- [AnnotatedElement — Reflection API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Documented API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Documented.html).
