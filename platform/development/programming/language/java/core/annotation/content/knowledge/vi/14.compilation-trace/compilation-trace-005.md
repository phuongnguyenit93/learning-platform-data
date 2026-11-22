# Cách trình biên dịch biểu diễn annotation lặp bằng kiểu chứa (container)

Một annotation Java thông thường chỉ được xuất hiện một lần tại một vị trí khai báo. Từ Java 8, `@Repeatable` cho phép cùng một annotation type xuất hiện **nhiều lần trên cùng một khai báo hoặc vị trí hợp lệ**. Nhưng câu hỏi quan trọng ở **dấu vết biên dịch** là: compiler lưu nhiều lần dùng đó vào file `.class` bằng cách nào?

**Đáp án cốt lõi:** khi một loại annotation `T` lặp lại, Java sử dụng **một annotation container** `TC` đã được lập trình viên khai báo. Trong container, phần tử bắt buộc `T[] value()` chứa các lần dùng `@T` theo thứ tự. Khi biên dịch nhiều `@T` ở cùng vị trí, compiler biểu diễn chúng **gián tiếp thông qua một lần dùng `@TC`**, thay vì ghi nhiều annotation `@T` độc lập trên cùng cấu trúc declaration annotation của class file. Vì vậy, muốn nhìn thấy biểu diễn thực tế, phải quan sát bytecode bằng `javap -v` hoặc một trình đọc class file; khi dùng Reflection, cần phân biệt API trả container với API tự mở container.

Bài này đi theo luồng **khai báo type → sử dụng lặp ở source → compiler kiểm tra và tạo biểu diễn container → thuộc tính class file → Reflection/bytecode reader**, đồng thời chỉ rõ sự khác biệt giữa một lần dùng, nhiều lần dùng và container được viết tường minh.

## 1. Hai annotation type, một mối quan hệ đặc biệt

Ví dụ đơn giản:

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

Trong đó:

- `Tag` là **annotation type được phép lặp**. Phần tử `Tag.value()` là `String`, biểu diễn một giá trị của **một** `@Tag`.
- `Tags` là **containing annotation type** (container). Phần tử `Tags.value()` là **`Tag[]`**, tức một mảng chứa các annotation `Tag`.
- `@Repeatable(Tags.class)` trên **định nghĩa `Tag`** khai báo mối quan hệ giữa annotation được lặp và container.
- `Tags` **không được compiler tự sinh ra**: người viết phải định nghĩa loại này trước. Compiler chỉ sử dụng định nghĩa ấy để biểu diễn các lần dùng lặp.

Có thể hình dung hai cấp:

```text
@Tag("java")                   -> một Tag, Tag.value() là String

@Tags({
    @Tag("java"),
    @Tag("core")
})                             -> một Tags, Tags.value() là Tag[2]
```

`String value()` của `Tag` và `Tag[] value()` của `Tags` cùng tên `value` nhưng thuộc **hai annotation type khác nhau**. Nhầm hai kiểu này là nguyên nhân phổ biến khiến compiler từ chối `@Repeatable`.

Tên container `Tags` không đặc biệt: `TagContainer` cũng hợp lệ nếu dùng nhất quán trong `@Repeatable(TagContainer.class)`. Nhưng **tên phần tử `value()` trong container là bắt buộc**, không thể đổi thành `items()`.

## 2. Từ hai annotation ở source tới một container trong class file

Xét source:

```java
@Tag("red")
@Tag("blue")
class Multi {
}
```

Khi compiler phân tích, nó xác minh rằng `Tag` thực sự repeatable, `Tags` là container hợp lệ, những lần dùng đều ở vị trí được phép và giá trị `"red"`, `"blue"` phù hợp kiểu phần tử `String`.

Về ý nghĩa biểu diễn, hai lần xuất hiện này tương đương với:

```java
@Tags({
    @Tag("red"),
    @Tag("blue")
})
class Multi {
}
```

Nhưng điều này **không có nghĩa compiler sửa file nguồn của bạn**, tạo file Java mới, hay tạo một class `Tags` hộ bạn. Nó là **quy tắc biên dịch/biểu diễn metadata**: trong class file cho vị trí declaration đó, container biểu diễn các annotation lặp.

Sơ đồ:

```text
Multi.java:
    @Tag("red")
    @Tag("blue")
    class Multi {}

        | javac kiểm tra @Repeatable, @Target, @Retention
        v

Multi.class:
    annotation type Tags
        value: annotation array
            [0] Tag(value="red")
            [1] Tag(value="blue")

        | nếu Tags và Tag có retention RUNTIME
        v

Multi.class.getDeclaredAnnotations():
    [Tags]

Multi.class.getDeclaredAnnotationsByType(Tag.class):
    [Tag("red"), Tag("blue")]
```

**Thứ tự** những annotation `Tag` lặp có ý nghĩa trong biểu diễn mảng: chúng được giữ theo thứ tự ở vị trí source. Nếu code xử lý nghiệp vụ cần ưu tiên giữa các tag, vẫn nên ghi rõ hợp đồng ưu tiên, thay vì coi thứ tự là một cơ chế xử lý tự động.

### Biểu diễn là container, không phải nhiều kiểu chứa

Nếu có ba `@Tag`, compiler vẫn dùng container có **`Tag[3]`**. Không cần `Tags2`, `Tags3` hay một container cho mỗi lần xuất hiện. Mỗi element trong mảng là một **annotation value**, không phải chuỗi thuần.

Một annotation đơn lẻ có thể chứa nhiều element:

```java
@Repeatable(Rules.class)
@interface Rule {
    String field();
    int order();
}

@interface Rules {
    Rule[] value();
}
```

Với:

```java
@Rule(field = "name", order = 1)
@Rule(field = "email", order = 2)
class Form {
}
```

container `Rules` mang mảng hai annotation `Rule`, mỗi phần tử giữ nguyên các element `field` và `order`. Compiler **không chuyển chúng thành hai mảng tách biệt** kiểu `String[] fields()` và `int[] orders()`.

## 3. Chữ ký container mà javac bắt buộc kiểm tra

Để `@Repeatable(Container.class)` hợp lệ cho loại `T`, `Container` phải là **annotation type** có phần tử:

```java
T[] value();
```

Các điều kiện quan trọng:

| Điều kiện | Cách hiểu |
| --- | --- |
| Tên element là `value` | Không thể đổi sang `entries`, `items`, `tags` |
| Kiểu trả về đúng `T[]` | Không được dùng `String[]`, `Object[]`, `T` hay `T[][]` |
| Mảng **một chiều** | Annotation element không hỗ trợ kiểu mảng nhiều chiều |
| Không có tham số | `value()` chứ không phải `value(int i)` |
| Các element bổ sung phải có `default` | Compiler phải tạo container từ các lần `@T` lặp mà không cần cung cấp element bổ sung |
| Container có retention/target/meta-annotations tương thích | Tránh mất thông tin hoặc dùng container ở vị trí không hợp lệ |

Ví dụ hợp lệ với một element phụ có mặc định:

```java
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
    String source() default "manual";
}
```

Ví dụ **không hợp lệ** nếu coi `WrongTags` là container cho `Tag`:

```java
@Repeatable(WrongTags.class)
@interface Tag {
    String value();
}

@interface WrongTags {
    String[] value(); // Sai: compiler yêu cầu Tag[].
}
```

Đây là đoạn cố ý sai, không phải code để chạy. Việc `Tag.value()` trả `String` **không** đồng nghĩa container được trả `String[]`.

Các dạng sai khác:

```java
// Chỉ minh họa lỗi trong những khai báo container riêng biệt.
// Tên phần tử sai:
Tag[] items();

// Không phải mảng:
Tag value();

// Mảng nhiều chiều:
Tag[][] value();

// Element phụ bắt buộc không có mặc định:
String source();
```

Những dòng này là **chữ ký minh họa**, không đặt độc lập ngoài `@interface` để biên dịch. Với `T[][]`, ngay bản thân kiểu phần tử annotation đã không hợp lệ.

## 4. @Retention: container được ghi vào thuộc tính class file nào?

Một cặp khai báo có `@Retention(RetentionPolicy.RUNTIME)` trên cả annotation chính và container:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}
```

Khi nhiều `@Tag` xuất hiện trên **class declaration**, metadata container sẽ được lưu trong thuộc tính class file **`RuntimeVisibleAnnotations`**. Với retention `CLASS`, nó được ghi trong **`RuntimeInvisibleAnnotations`**. Với retention `SOURCE`, các lần dùng annotation không được lưu thành annotation metadata trong `.class`.

| Retention của repeated annotation và container | Dấu vết declaration annotation trong `.class` | Reflection chuẩn |
| --- | --- | --- |
| `SOURCE` / `SOURCE` | Không giữ annotation này trong class file | Không đọc được |
| `CLASS` / `CLASS` | Container trong `RuntimeInvisibleAnnotations` | Không đọc được |
| `RUNTIME` / `RUNTIME` | Container trong `RuntimeVisibleAnnotations` | Đọc được với API thích hợp |

Các dòng này giả định các annotation được gắn lên **khai báo class**, không phải type-use hoặc parameter. Class file có các thuộc tính chuyên biệt như `RuntimeVisibleParameterAnnotations`, `RuntimeInvisibleParameterAnnotations`, `RuntimeVisibleTypeAnnotations` và `RuntimeInvisibleTypeAnnotations` cho những vị trí tương ứng.

**Retention phải tương thích.** Container không được có retention **ngắn hơn** repeated annotation: nếu `Tag` dùng `RUNTIME`, `Tags` cũng phải dùng `RUNTIME`. Nếu `Tag` dùng `CLASS`, `Tags` có thể dùng `CLASS` hoặc `RUNTIME` theo luật ngôn ngữ; không nên dựa vào lựa chọn khác nhau nếu không có nhu cầu rõ ràng.

Nếu không khai báo `@Retention`, mặc định là `CLASS`, không phải `RUNTIME`.

### Vì sao RuntimeInvisibleAnnotations vẫn chứa annotation?

Tên thuộc tính dễ gây hiểu nhầm:

- `RuntimeVisibleAnnotations` nghĩa là metadata trong class file được dành cho annotation **runtime-visible**, ví dụ có retention `RUNTIME`.
- `RuntimeInvisibleAnnotations` nghĩa là metadata có trong class file nhưng **không được Java Reflection chuẩn hiển thị**.
- “Invisible” không có nghĩa không nằm trong class file; công cụ như `javap` hoặc bytecode reader vẫn có thể quan sát.

`@Repeatable` không làm annotation mặc định chuyển từ `CLASS` sang `RUNTIME` và cũng không tự giúp Reflection đọc annotation có retention `CLASS`.

## 5. Ví dụ Java 17+ hoàn chỉnh để xem cả source, bytecode và Reflection

Tạo file duy nhất **`CompilerContainerDemo.java`**:

```java
import java.lang.annotation.*;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("red")
@Tag("blue")
class Multi {
}

@Tag("solo")
class Single {
}

@Tags({@Tag("manual-one"), @Tag("manual-two")})
class Explicit {
}

@Tags({})
class Empty {
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@Repeatable(BuildMarks.class)
@interface BuildMark {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface BuildMarks {
    BuildMark[] value();
}

@BuildMark("first")
@BuildMark("second")
class BuildOnly {
}

public class CompilerContainerDemo {
    static void show(Class<?> type) {
        String[] declared = Arrays.stream(type.getDeclaredAnnotations())
                .map(a -> a.annotationType().getSimpleName())
                .toArray(String[]::new);

        String[] tags = Arrays.stream(type.getDeclaredAnnotationsByType(Tag.class))
                .map(Tag::value)
                .toArray(String[]::new);

        System.out.println(type.getSimpleName()
                + " | direct=" + Arrays.toString(declared)
                + " | Tag=" + Arrays.toString(tags));
    }

    public static void main(String[] args) {
        show(Multi.class);
        show(Single.class);
        show(Explicit.class);
        show(Empty.class);

        System.out.println("BuildOnly visible="
                + BuildOnly.class.getDeclaredAnnotations().length);
    }
}
```

Biên dịch trong thư mục chứa file bằng JDK 17 trở lên:

```bash
javac --release 17 CompilerContainerDemo.java
java CompilerContainerDemo
```

Stdout:

```text
Multi | direct=[Tags] | Tag=[red, blue]
Single | direct=[Tag] | Tag=[solo]
Explicit | direct=[Tags] | Tag=[manual-one, manual-two]
Empty | direct=[Tags] | Tag=[]
BuildOnly visible=0
```

**Kết quả trên đã được kiểm chứng:** toàn bộ file được biên dịch với `javac --release 17` và chạy, stdout trùng khớp. Chương trình không yêu cầu thư viện ngoài JDK.

### 5.1. Phân tích Multi

`Multi` có hai `@Tag` cùng loại. Compiler biểu diễn chúng qua container `Tags`.

- `getDeclaredAnnotations()` nhìn thấy **một `Tags`** tại runtime.
- `getDeclaredAnnotationsByType(Tag.class)` **mở container**, trả **hai `Tag`** có `value()` tương ứng `"red"` và `"blue"`.
- `getDeclaredAnnotation(Tag.class)` sẽ **không tự mở container** và trong ví dụ `Multi` trả `null`.
- `getDeclaredAnnotation(Tags.class)` trả container để bạn có thể tự đọc `value()` nếu cần.

### 5.2. Phân tích Single

`Single` chỉ dùng một `@Tag("solo")`. Một lần sử dụng không buộc phải có container.

- `getDeclaredAnnotations()` trả `Tag` chứ không phải `Tags`.
- `getDeclaredAnnotationsByType(Tag.class)` vẫn trả một `Tag`.
- `getDeclaredAnnotation(Tags.class)` trả `null` trong trường hợp này.

**Không được giả định mọi lần dùng một repeatable annotation đều được chứa trong container.** Tình huống một lần và nhiều lần có biểu diễn vật lý khác nhau.

### 5.3. Phân tích Explicit

`Explicit` tự viết:

```java
@Tags({@Tag("manual-one"), @Tag("manual-two")})
class Explicit {
}
```

Dù không dùng cú pháp lặp trực tiếp, trên class vẫn có một container `Tags`. Reflection có thể mở container và lấy hai `Tag`.

### 5.4. Phân tích Empty

`@Tags({})` đặt **container hợp lệ với mảng rỗng**. `getDeclaredAnnotations()` thấy `Tags`, còn `getDeclaredAnnotationsByType(Tag.class)` trả mảng `Tag[0]`. Có container không đồng nghĩa trong đó có ít nhất một annotation lặp.

### 5.5. Phân tích BuildOnly

`BuildMark` và `BuildMarks` có retention `CLASS`. Compiler vẫn ghi container vào class file cho `BuildOnly`, nhưng Java Reflection tiêu chuẩn không trả metadata `CLASS`, nên `BuildOnly.class.getDeclaredAnnotations().length` là `0`.

**Không được suy ra “BuildOnly không có BuildMark trong class file” từ dòng `0`.** Dùng `javap` ở mục tiếp theo để kiểm tra dấu vết biên dịch.

## 6. Dùng javap -v để xem dấu vết container trong .class

Sau khi biên dịch `CompilerContainerDemo.java`, chạy:

```bash
javap -v -p Multi
javap -v -p Single
javap -v -p Explicit
javap -v -p Empty
javap -v -p BuildOnly
```

Chạy tại thư mục chứa các file `.class`. Nếu biên dịch vào thư mục riêng, ví dụ `javac --release 17 -d out CompilerContainerDemo.java`, bổ sung `-classpath out` vào `javap` và `java -cp out CompilerContainerDemo`.

### 6.1. Multi.class: chỉ một annotation container ở lớp khai báo

Tìm trong output của `javap -v -p Multi` phần:

```text
RuntimeVisibleAnnotations:
    ... Tags(
        value=[...Tag(value="red"), ...Tag(value="blue")]
    )
```

Khối trên là **diễn giải có lược bỏ**, không phải bản sao từng ký tự của output `javap`. `javap` thường in chỉ số constant pool, dạng descriptor và vị trí mảng. Những thứ cần xác định là:

1. Có thuộc tính `RuntimeVisibleAnnotations` trên `Multi.class`.
2. Annotation được mã hóa trên declaration này là **`Tags`**.
3. Phần tử `value` chứa **hai annotation value loại `Tag`**, kèm các chuỗi `"red"` và `"blue"`.

Bạn không nên mong tìm hai entry `Tag` độc lập song song trong danh sách top-level `RuntimeVisibleAnnotations` của lớp `Multi`.

### 6.2. Single.class: một annotation Tag trực tiếp

Với `javap -v -p Single`, sẽ thấy annotation `Tag` trong `RuntimeVisibleAnnotations`, không phải container `Tags` được compiler tạo chỉ vì `Tag` có `@Repeatable`.

Đây là khác biệt quan trọng giữa **annotation type hỗ trợ lặp** và **lần sử dụng thực sự có lặp**.

### 6.3. Explicit.class và Empty.class

- `Explicit.class` chứa `Tags` với hai `Tag` trong mảng `value` vì source đã viết container tường minh.
- `Empty.class` chứa `Tags` với mảng `value` rỗng.

Công cụ phân tích bytecode không nên coi “gặp container” là bằng chứng có nhiều annotation con: phải đọc **mảng `value`** và độ dài của nó.

### 6.4. BuildOnly.class: RuntimeInvisibleAnnotations

`javap -v -p BuildOnly` cho thấy container `BuildMarks` trong:

```text
RuntimeInvisibleAnnotations:
    ... BuildMarks(
        value=[...BuildMark(value="first"), ...BuildMark(value="second")]
    )
```

Đây cũng là sơ đồ lược bỏ chứ không phải output verbatim. Dấu vết này xác nhận **retention CLASS giữ metadata trong .class** nhưng không làm nó đọc được qua Reflection chuẩn.

### 6.5. Đừng nhầm file của annotation type với file của lớp được đánh dấu

Nếu chạy `javap -v Tag`, bạn đang xem **định nghĩa annotation type `Tag`**, nơi có meta-annotation `@Repeatable(Tags.class)`. Đây không phải cùng metadata với **hai lần dùng `@Tag` trên `Multi`**.

Cần phân biệt:

| File đang xem | Điều cần tìm |
| --- | --- |
| `Tag.class` | Meta-annotation khai báo quan hệ `@Repeatable(Tags.class)` |
| `Tags.class` | Định nghĩa annotation container có `Tag[] value()` |
| `Multi.class` | Một lần sử dụng container `Tags` có mảng hai `Tag` |
| `Single.class` | Một lần sử dụng `Tag` trực tiếp |
| `BuildOnly.class` | Container `BuildMarks` ở thuộc tính runtime-invisible |

Trên các compiler/JDK khác nhau, chỉ số constant pool và thứ tự hiển thị có thể khác, nhưng **ý nghĩa của cấu trúc container** vẫn theo quy tắc của Java.

## 7. API Reflection nào khôi phục danh sách annotation lặp?

Khi retention là `RUNTIME`, Java Reflection có hai nhóm API cần phân biệt:

| API | Ý nghĩa trong ví dụ `Multi` |
| --- | --- |
| `getDeclaredAnnotations()` | Thấy `Tags` như một annotation trực tiếp của class |
| `getDeclaredAnnotation(Tag.class)` | Không tự mở container, trả `null` |
| `getDeclaredAnnotation(Tags.class)` | Trả `Tags`, gọi `value()` được mảng hai `Tag` |
| `getDeclaredAnnotationsByType(Tag.class)` | Tự đọc annotation trực tiếp/gián tiếp, trả `Tag[2]` |
| `getAnnotationsByType(Tag.class)` | Cũng trả `Tag[2]` trong ví dụ này; có thêm quy tắc `@Inherited` khi phù hợp |
| `getAnnotation(Tag.class)` | Không phải “phần tử đầu tiên trong container”; không phải API phù hợp để đọc nhiều `Tag` |

Chọn API theo câu hỏi:

- Cần **tất cả annotation `Tag`** trên class được đánh dấu, bất kể một lần, nhiều lần hay container tường minh? Dùng `getDeclaredAnnotationsByType(Tag.class)` nếu chỉ xét chính declaration đó.
- Muốn xét thêm **quy tắc thừa kế class** khi loại annotation có `@Inherited`? Dùng `getAnnotationsByType(Tag.class)`.
- Muốn truy vấn **bản thân container**? Dùng `getDeclaredAnnotation(Tags.class)` và `value()`.
- Chỉ gọi `getAnnotation(Tag.class)` và thấy `null` **không đủ để kết luận** không có `Tag` lặp: container có thể đang lưu chúng.

Cơ chế “mở” container là logic của **Reflection theo loại annotation**, không phải việc Java tự thay đổi bytecode vào lúc bạn gọi `getAnnotationsByType`.

## 8. Compiler không cho phép lặp tùy ý: cần container hợp lệ

`@Repeatable` vừa cho phép cú pháp lặp, vừa áp đặt điều kiện compile-time cho cặp type. Các lỗi thường gặp:

### 8.1. Quên @Repeatable

```java
@interface Note {
    String value();
}

@Note("a")
@Note("b")
class Example {
}
```

Đây là đoạn **cố ý sai**. Chỉ có `@interface Note` với phần tử `value` không làm nó repeatable. Dù bạn định nghĩa `Notes { Note[] value(); }` riêng, vẫn phải gắn `@Repeatable(Notes.class)` lên `Note`.

### 8.2. Container không có phần tử value() đúng kiểu

```java
@Repeatable(Notes.class)
@interface Note {
    String value();
}

@interface Notes {
    String[] value(); // Sai: phải là Note[] value().
}
```

Compiler từ chối vì `String[]` không phải kiểu mảng annotation `Note[]` mà quan hệ `@Repeatable` yêu cầu.

### 8.3. Container có element bổ sung không có default

```java
@Repeatable(Notes.class)
@interface Note {
    String value();
}

@interface Notes {
    Note[] value();
    String owner(); // Sai khi Notes là container: thiếu default.
}
```

Compiler không thể tự điền `owner` khi nhóm các `@Note` lặp. Có thể sửa thành `String owner() default "system";` nếu phần tử bổ sung thực sự cần thiết.

### 8.4. Retention của container ngắn hơn annotation chính

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Notes.class)
@interface Note {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface Notes {
    Note[] value();
}
```

Cấu hình **không hợp lệ** vì container được giữ ngắn hơn annotation chính. Khi cần Reflection, cả hai nên dùng `RUNTIME`.

### 8.5. Target không tương thích

Nếu `Note` được dùng trên method, container phải hợp lệ để chứa những lần `@Note` ở vị trí method. Ví dụ đặt cùng:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Notes.class)
@interface Note {
    String value();
}

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Notes {
    Note[] value();
}
```

Đây là cấu hình vị trí tương thích. Nếu khác target một cách không hợp lệ, compiler từ chối quan hệ repeatable. Các vị trí `TYPE_USE`, `TYPE_PARAMETER`, `PARAMETER` và các loại declaration có thêm quy tắc cụ thể; không kết luận mọi tập target là tương thích chỉ vì “trông gần giống”.

### 8.6. @Inherited và @Documented

Nếu annotation chính dùng `@Inherited`, container cũng phải có `@Inherited`. Tương tự, nếu annotation chính có `@Documented`, container cũng cần `@Documented`. Những meta-annotation này được compiler xét cùng quan hệ containing type.

Tuy nhiên **`@Inherited` không khiến các annotation trên method, parameter hoặc interface tự truyền theo quan hệ kế thừa**. Nó có phạm vi riêng trên class và các phép tra cứu Reflection thích hợp.

## 9. Một lần dùng, lặp trực tiếp và container tường minh khác gì nhau?

Các trường hợp cùng sử dụng một cặp `Tag`/`Tags`:

| Source | Kiểu annotation trực tiếp trong class file trên declaration | `getDeclaredAnnotationsByType(Tag.class)` |
| --- | --- | --- |
| `@Tag("solo")` | `Tag` | `[Tag("solo")]` |
| `@Tag("a") @Tag("b")` | `Tags` với `Tag[2]` | `[Tag("a"), Tag("b")]` |
| `@Tags({@Tag("a"), @Tag("b")})` | `Tags` tường minh | `[Tag("a"), Tag("b")]` |
| `@Tags({})` | `Tags` với mảng rỗng | `[]` |
| Không gắn annotation | Không có `Tag`/`Tags` tại declaration | `[]` |

Hệ quả cho code đọc metadata: **không nên chỉ kiểm tra có container hay không** rồi coi đó là điều kiện cần để có repeatable annotation. Một `@Tag` đơn lẻ có thể nằm trực tiếp mà không có container.

Trong điều kiện cần đọc cả đơn và lặp, dùng `getDeclaredAnnotationsByType(Tag.class)` là cách đơn giản, trong khi công cụ đọc bytecode phải biết xử lý **cả dạng trực tiếp lẫn dạng container**.

## 10. Gắn annotation lặp ở parameter hoặc type-use có gì khác?

Cơ chế containing annotation type vẫn là: `@Repeatable(Container.class)` và **`T[] value()`**. Nhưng cấu trúc class file chứa metadata phụ thuộc **vị trí gắn**.

Ví dụ khai báo trên tham số phương thức:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@Repeatable(Args.class)
@interface Arg {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Args {
    Arg[] value();
}

class Endpoint {
    void handle(@Arg("required") @Arg("public") String name) {
    }
}
```

Đây là snippet minh họa, cần import các loại trong `java.lang.annotation` như ví dụ chính.

Ở class file, container cho parameter annotation nằm trong metadata **parameter annotations** thích hợp, chẳng hạn `RuntimeVisibleParameterAnnotations`, chứ không nhất thiết là thuộc tính top-level `RuntimeVisibleAnnotations` của class.

Khi đọc bằng Reflection:

```java
java.lang.reflect.Method method =
        Endpoint.class.getDeclaredMethod("handle", String.class);

java.lang.reflect.Parameter parameter = method.getParameters()[0];

Arg[] values = parameter.getAnnotationsByType(Arg.class);
System.out.println(values.length); // 2
```

Cần tách vị trí:

- **Annotation khai báo trên parameter:** `Parameter.getAnnotationsByType(Arg.class)`.
- **Annotation gắn lên kiểu của parameter (`TYPE_USE`):** cần dùng `Parameter.getAnnotatedType()` và API về `AnnotatedType` phù hợp; metadata nằm trong nhóm type annotations tương ứng.

Không vì tên thuộc tính đều chứa “Annotations” mà coi mọi annotation đều nằm ở class-level. Khi dùng `javap -v`, đọc đúng phần khai báo method và đúng vị trí.

## 11. Tại sao compiler không viết nhiều entry top-level Tag?

Class-file annotation metadata có cấu trúc biểu diễn theo **annotation type** và danh sách cặp **element-name/value**. Container là cách tiêu chuẩn để mô tả một danh sách các annotation có cùng loại tại một vị trí, đồng thời giữ chữ ký metadata được công bố trong chương trình Java.

Nhờ container:

1. **Compiler kiểm tra loại chứa:** `Tags.value()` phải là `Tag[]`.
2. **Dữ liệu có kiểu rõ ràng:** từng `Tag` vẫn có `value()` hoặc các element khác của nó.
3. **Duy trì thứ tự lặp:** các annotation lặp được biểu diễn bằng vị trí phần tử trong mảng.
4. **Công cụ đọc bytecode có cấu trúc để giải mã:** đọc container, lấy mảng annotation values.
5. **Reflection có thể trình bày lại dạng thuận tiện:** `getAnnotationsByType(Tag.class)` trả mảng `Tag[]` phù hợp logic ứng dụng.

Dù vậy, **compiler không tự thực thi hành vi ứng dụng** vì annotation xuất hiện. Ví dụ `@Tag("red")` không tự in `red`; chương trình phải có consumer đọc metadata rồi làm việc với nó.

## 12. Công cụ đọc class file cần xử lý hai dạng biểu diễn

Nếu tự xây công cụ phân tích bytecode (hoặc dùng thư viện như ASM), hãy tránh giả định chỉ có annotation được lặp hoặc chỉ có container.

Ý tưởng xử lý:

```text
Với annotation type T và container TC:
    đọc annotation metadata trên đúng vị trí
    nếu thấy annotation type T trực tiếp:
        nhận một T
    nếu thấy TC:
        đọc element "value" kiểu T[]
        nhận từng T trong mảng theo thứ tự
    lưu ý retention SOURCE/CLASS/RUNTIME
    lưu ý class declaration, method, parameter, type-use
```

Sơ đồ là **thuật toán định hướng**, không phải mã Java chạy độc lập. Với những cấu hình phức tạp, framework còn cần quan tâm `@Inherited`, nhiều superclass, và cách xử lý annotation cùng kiểu từ cha/con. Việc **gộp metadata của nhiều tầng** không tự động xảy ra chỉ nhờ cú pháp `@Repeatable`.

Nếu công cụ chỉ tìm annotation trực tiếp có descriptor `L.../Tag;` mà không xử lý `Tags`, nó sẽ **bỏ sót các trường hợp lặp** được compiler đóng gói. Ngược lại, nếu chỉ tìm `Tags` thì bỏ sót một `@Tag` đơn lẻ.

**Cẩn thận về retention:** bytecode reader có thể đọc annotation `CLASS` từ `RuntimeInvisibleAnnotations`, nhưng Java Reflection chuẩn không đọc được annotation ấy. Nếu không có `RUNTIME`, đừng thử sửa bằng cách đổi `getAnnotation` thành `getAnnotationsByType`; cả hai đều phụ thuộc khả năng runtime visibility phù hợp.

## 13. Không nên suy luận sai về annotation processor

Một annotation processor chạy trong quá trình biên dịch và dùng model từ `javax.lang.model` có thể làm việc với repeated annotations, nhưng **model ở compile-time không đơn giản là một bản sao của Reflection runtime**.

- `getAnnotationMirrors()` làm việc với mô hình annotation trong quá trình biên dịch; kết quả và biểu diễn trực tiếp/container cần được hiểu theo hợp đồng API và giai đoạn xử lý.
- Các API `getAnnotationsByType(...)` trên những phần tử thích hợp có mục đích đọc annotation theo loại, bao gồm repeatable annotations theo ngữ nghĩa được quy định.
- `javap -v` xem **dấu vết class file đầu ra**, là cách phù hợp nhất để quan sát biểu diễn container sau compile.

Không lấy kết quả Reflection runtime làm bằng chứng tuyệt đối về thứ tự callback hoặc cách processor nào đó duyệt annotation mirrors. Nếu bài toán cụ thể là annotation processing, cần kiểm chứng riêng hành vi processor với phiên bản compiler/API được dùng.

## 14. Lỗi hiểu sai thường gặp

**“`@Repeatable` khiến javac tự sinh class container.”** Sai. `Tags` phải được khai báo sẵn và có `Tag[] value()`. Compiler sử dụng nó để đóng gói các lần dùng.

**“Hai `@Tag` sẽ vẫn là hai annotation trực tiếp tách rời trong `Multi.class`.”** Sai với biểu diễn declaration annotation của ví dụ: chúng được chứa trong `@Tags`.

**“Chỉ một `@Tag` cũng luôn chuyển thành `@Tags({@Tag(...)})`.”** Sai. Một lần dùng thường được giữ trực tiếp; kiểm tra ví dụ `Single`.

**“Container có `String[] value()` vì `Tag.value()` trả `String`.”** Sai. Container phải trả mảng **các annotation `Tag`**, tức `Tag[]`.

**“Có `@Tags` thì chắc chắn có ít nhất hai `@Tag`.”** Sai. Có thể có một phần tử hoặc mảng rỗng; `@Tags({})` minh họa mảng rỗng.

**“`getAnnotation(Tag.class)` trả `null` tức Multi không có tag.”** Sai. Dùng `getAnnotationsByType(Tag.class)` hoặc đọc `Tags`.

**“Annotation có retention CLASS thì không nằm trong .class.”** Sai. Nó có trong class file và có thể thấy bằng `javap`, chỉ không xuất hiện qua Java Reflection chuẩn.

**“Cứ có `@Repeatable` thì dữ liệu tự truy vấn được lúc chạy.”** Sai. Phải chọn retention phù hợp (thường `RUNTIME` cho cả hai) và có code đọc annotation.

**“`@Inherited` làm annotation lặp trên interface hoặc method tự truyền xuống.”** Sai. Ngữ nghĩa inherited chỉ áp dụng phù hợp với quan hệ superclass và API Reflection trên class.

**“Thấy container trong class file thì chắc chắn đó là cách viết ở source.”** Sai. Source có thể dùng nhiều `@Tag` trực tiếp **hoặc** một `@Tags({...})` tường minh; class file có thể biểu diễn cả hai thông qua container. Không thể suy đoán chắc chắn cú pháp source ban đầu chỉ từ sự hiện diện của một container.

## 15. Bài tập thực hành

### Bài 1 — Dự đoán dạng bytecode

Cho cặp `@Repeatable(Checks.class) @interface Check { int value(); }` và `@interface Checks { Check[] value(); }`, đặt hai lần `@Check(1) @Check(2)` lên một class. Trong metadata declaration của class file, bạn mong thấy loại annotation nào và `value()` chứa gì?

**Đáp án:** container `Checks` có mảng hai annotation `Check`. Mỗi `Check` có giá trị `int` riêng (`1`, `2`).

### Bài 2 — Một lần không có container

Tại sao `Single.class.getDeclaredAnnotation(Tags.class)` có thể trả `null` nhưng `Single.class.getDeclaredAnnotationsByType(Tag.class).length` bằng `1`?

**Đáp án:** một `@Tag` trực tiếp không cần container. API by-type vẫn lấy được nó.

### Bài 3 — Retention CLASS

Trên `BuildOnly.class` của ví dụ chính, `getDeclaredAnnotations().length` bằng `0`. Lệnh nào thích hợp để xác minh `BuildMarks` có mặt trong class file?

**Đáp án:** `javap -v -p BuildOnly`, kiểm tra `RuntimeInvisibleAnnotations`.

### Bài 4 — Nhận diện lỗi compiler

Tìm lỗi:

```java
@Repeatable(Checks.class)
@interface Check {
    String value();
}
@interface Checks {
    String[] value();
}
```

**Đáp án:** `Checks.value()` phải là **`Check[] value()`**, không phải `String[]`.

### Bài 5 — Annotation trên parameter

Với `@Arg("required") @Arg("public") String name` trong mục 10, Reflection muốn lấy hai annotation `Arg` nên dùng `Parameter.getAnnotation(Arg.class)` hay `Parameter.getAnnotationsByType(Arg.class)`?

**Đáp án:** dùng `getAnnotationsByType(Arg.class)`, vì `getAnnotation` không tự mở container để tạo danh sách hai phần tử.

### Bài 6 — Truy vết compiler

Bạn chỉ có `Multi.class` và không có source. `javap` cho thấy container `Tags` có hai `Tag`. Bạn có kết luận chắc source viết hai dòng `@Tag` thay vì một `@Tags({...})` không?

**Đáp án:** không. Hai cú pháp có thể tạo dấu vết container tương tự. Biểu diễn nhị phân cho biết cấu trúc metadata, không nhất thiết phục hồi nguyên vẹn cú pháp nguồn.

### Bài 7 — Công cụ quét bytecode

Một bytecode scanner chỉ tìm descriptor của `Tag` tại danh sách top-level runtime-visible annotations trên class. Vì sao nó có thể bỏ sót `Multi` và vẫn thấy `Single`?

**Đáp án:** `Multi` được biểu diễn trực tiếp bằng `Tags`, còn `Single` có `Tag` trực tiếp. Scanner cần nhận biết cả repeated type và containing type, sau đó đọc `Tags.value()`.

## 16. Checklist xác minh dấu vết annotation lặp

1. **Xác định annotation type T:** nó có `@Repeatable(Container.class)` không?
2. **Kiểm tra container:** có `T[] value()` đúng tên, đúng kiểu, một chiều và các element khác có default không?
3. **Kiểm tra meta-annotations:** retention, target, `@Inherited`, `@Documented` có tương thích không?
4. **Đếm số lần dùng ở source:** một `@T`, nhiều `@T` hay container tường minh?
5. **Biên dịch:** dùng `javac --release 17` hoặc phiên bản JDK thích hợp, xử lý mọi lỗi kiểu trước khi đọc bytecode.
6. **Quan sát đúng class file:** dùng `javap -v -p` tại lớp được đánh annotation, không nhầm với file định nghĩa `T.class`.
7. **Tìm đúng thuộc tính:** runtime-visible/invisible của declaration, parameter hoặc type-use tùy target.
8. **Đọc mảng `value`:** đếm và xác minh từng annotation con, không chỉ kiểm tra có container.
9. **Đọc bằng Reflection nếu retention RUNTIME:** so sánh `getDeclaredAnnotations()` với `getDeclaredAnnotationsByType(T.class)` để thấy sự khác nhau giữa biểu diễn vật lý và truy vấn theo loại.
10. **Không tự suy ra hành vi nghiệp vụ:** annotation là metadata; chương trình hoặc công cụ muốn dùng nó phải triển khai logic tiêu thụ.

**Kết luận:** `@Repeatable` không yêu cầu JVM giữ nhiều annotation giống nhau như các entry top-level độc lập trên cùng declaration. Khi **nhiều** annotation type `T` được viết lặp, compiler dùng **container được khai báo sẵn** với chữ ký **`T[] value()`** để biểu diễn chúng. Class-file tooling nhìn thấy container và mảng bên trong; Reflection có các API `getAnnotationsByType` để trình bày lại các annotation `T`. Hiểu cả hai góc nhìn giúp giải thích vì sao một annotation đơn lẻ, nhiều annotation lặp và container tường minh có biểu diễn khác nhau mà vẫn có thể cho cùng kiểu kết quả khi truy vấn theo loại.