# RetentionPolicy.CLASS: annotation được lưu trong class file nhưng Reflection chuẩn không đọc được

Một annotation trong Java có thể hữu ích **sau khi biên dịch** mà **không cần xuất hiện qua Reflection khi chương trình chạy**. Đây chính là ý nghĩa của `RetentionPolicy.CLASS`.

Với chính sách `CLASS`, compiler ghi thông tin về lần sử dụng annotation vào file `.class`. Công cụ đọc bytecode có thể tìm thấy thông tin ấy, nhưng các API Reflection chuẩn như `Class.getAnnotation(...)`, `getDeclaredAnnotation(...)` và `getDeclaredAnnotations()` **không trả về annotation có retention `CLASS`**. Điều này vẫn đúng khi JVM đã nạp lớp chứa annotation.

Đây là điểm thường gây nhầm lẫn: “nằm trong class file” và “truy vấn được từ đối tượng `Class<?>` bằng Reflection” là **hai khả năng khác nhau**.

## 1. Retention quyết định giữ annotation đến giai đoạn nào

Retention là **chính sách lưu giữ metadata annotation**. Java khai báo nó bằng meta-annotation `@Retention` trong `java.lang.annotation`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.CLASS)
@interface BuildMarker {
}
```

Tại đây:

- `BuildMarker` là một annotation type do chúng ta định nghĩa.
- `@Retention(RetentionPolicy.CLASS)` mô tả chính sách lưu giữ của **những lần sử dụng `@BuildMarker`**.
- `CLASS` giữ metadata trong `.class` do compiler tạo, nhưng không yêu cầu VM cung cấp annotation này cho Reflection.
- Meta-annotation này **không trực tiếp tạo ra hành vi nghiệp vụ**. Công cụ nào muốn xử lý `BuildMarker` phải tự đọc và áp dụng logic.

Ba giá trị của `RetentionPolicy`:

| Chính sách | Metadata trên lớp đã biên dịch | Reflection chuẩn khi chạy | Ví dụ mục đích |
| --- | --- | --- | --- |
| `SOURCE` | Không được giữ trong `.class` | Không đọc được | Phân tích/chỉ dẫn trong giai đoạn mã nguồn hoặc annotation processing |
| **`CLASS`** | **Được lưu trong `.class`** | **Không đọc được** | Công cụ đọc hoặc biến đổi bytecode sau compile |
| `RUNTIME` | Được lưu trong `.class` | Đọc được nếu thực sự có annotation thích hợp | Chương trình/framework truy vấn annotation qua Reflection |

Nếu không viết `@Retention` cho một annotation type, **giá trị mặc định là `RetentionPolicy.CLASS`**, không phải `RUNTIME`. Đây là mặc định của **khai báo annotation type**, không có nghĩa mọi annotation chuẩn Java đều dùng `CLASS`; từng annotation chuẩn có thể chọn retention khác.

Giữ annotation trong file `.class` giúp metadata có thể được dùng ở các bước xử lý bytecode mà không cần biến nó thành một phần của Reflection runtime API.

## 2. Dòng chảy của annotation có CLASS retention

Giả sử có:

```java
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface BuildHint {
    String value();
}

@BuildHint("verify-bytecode")
class Job {
}
```

Khi biên dịch `Job.java`:

1. Compiler phân tích mã Java và kiểm tra cú pháp/kiểu của `@BuildHint("verify-bytecode")`. Ví dụ `value()` trả `String` nên chuỗi là kiểu giá trị phù hợp.
2. Compiler tạo class file, ghi metadata `BuildHint` gắn lên `Job` theo biểu diễn annotation trong class file.
3. Công cụ biết đọc cấu trúc class file có thể tìm metadata đó để phân tích, lập chỉ mục hoặc biến đổi bytecode.
4. Nếu mã chạy gọi `Job.class.getAnnotation(BuildHint.class)`, Reflection chuẩn trả `null`. Nó không cung cấp lần sử dụng `@BuildHint` nói trên.
5. Không có đoạn mã nào được tự động gọi chỉ vì annotation xuất hiện trong `.class`.

Có thể hình dung:

```text
Job.java
  @BuildHint("verify-bytecode")
        |
        | javac: kiểm tra cách sử dụng annotation
        v
Job.class
  có annotation metadata (CLASS)
        |
        +----> công cụ đọc trực tiếp class file: có thể nhìn thấy
        |
        +----> JVM nạp Job.class
                    |
                    +----> Job.class.getAnnotation(BuildHint.class)
                                   |
                                   v
                                  null
```

Điểm quyết định nằm ở **cơ chế người tiêu thụ dùng để đọc metadata**:

- **Đọc class file/bytecode:** công cụ có thể đọc dữ liệu `CLASS`.
- **Dùng Java Reflection chuẩn trên lớp đã nạp:** không trả về dữ liệu `CLASS`.
- **Chỉ chạy chương trình:** không có xử lý annotation nào tự xảy ra nếu không có logic chủ động.

## 3. Ví dụ Java 17+ chạy được: cùng một lớp có SOURCE, CLASS và RUNTIME

Tạo tệp duy nhất **`ClassRetentionDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceHint {
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassHint {
    String value();
}

// Không khai báo @Retention: mặc định là CLASS.
@Target(ElementType.TYPE)
@interface DefaultHint {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeHint {
    String value();
}

@SourceHint
@ClassHint("bytecode")
@DefaultHint
@RuntimeHint("runtime")
class TaggedService {
}

public class ClassRetentionDemo {
    public static void main(String[] args) {
        Class<TaggedService> type = TaggedService.class;

        System.out.println(type.getDeclaredAnnotation(ClassHint.class));
        System.out.println(type.isAnnotationPresent(DefaultHint.class));
        System.out.println(type.getDeclaredAnnotation(RuntimeHint.class).value());
        System.out.println(type.getDeclaredAnnotations().length);

        // Đọc chính sách trên *kiểu annotation*, không phải
        // đọc lần sử dụng @ClassHint trên TaggedService.
        System.out.println(
                ClassHint.class.getAnnotation(Retention.class).value());
    }
}
```

Đặt terminal tại thư mục chứa file rồi chạy bằng JDK 17+:

```bash
javac --release 17 ClassRetentionDemo.java
java ClassRetentionDemo
```

Stdout chính xác:

```text
null
false
runtime
1
CLASS
```

**Vì sao mỗi dòng lại như vậy?**

1. `getDeclaredAnnotation(ClassHint.class)` trả `null` vì **lần sử dụng `@ClassHint` trên `TaggedService` có retention `CLASS`**.
2. `isAnnotationPresent(DefaultHint.class)` trả `false` vì `DefaultHint` không khai báo `@Retention` và do đó cũng dùng `CLASS`.
3. `getDeclaredAnnotation(RuntimeHint.class).value()` trả `"runtime"` vì lần sử dụng `@RuntimeHint` có retention `RUNTIME`.
4. `getDeclaredAnnotations().length` là `1`: trên `TaggedService`, chỉ `RuntimeHint` được Reflection chuẩn nhìn thấy trong bốn annotation được đặt ở source.
5. `ClassHint.class.getAnnotation(Retention.class).value()` trả `CLASS`. **Đây là một truy vấn khác:** nó đọc annotation `@Retention` gắn trên **định nghĩa của kiểu `ClassHint`**. `@Retention` bản thân được giữ đến runtime, nên có thể đọc nó bằng Reflection. Điều này **không** biến những lần sử dụng `@ClassHint` thành annotation có retention `RUNTIME`.

Ví dụ sử dụng các kiểu annotation cùng package mặc định để chạy độc lập trong một tệp. Tệp phải có tên `ClassRetentionDemo.java` vì chứa `public class ClassRetentionDemo`.

## 4. Kiểm chứng CLASS metadata thực sự nằm trong .class bằng javap

Sau khi biên dịch ví dụ trên, kiểm tra **chính file của lớp được đánh annotation**, không phải file của kiểu annotation:

```bash
javap -v -p TaggedService
```

`javap` là công cụ đi kèm JDK dùng để xem thông tin class file; `-v` hiển thị các chi tiết bytecode/class file, `-p` bao gồm cả các thành viên private khi có.

Trong phần chi tiết của **`TaggedService.class`**, hãy tìm những thuộc tính có tên:

```text
RuntimeInvisibleAnnotations:
    ... ClassHint ...
    ... DefaultHint ...

RuntimeVisibleAnnotations:
    ... RuntimeHint ...
```

Đây là **minh họa cấu trúc cần tìm**, không phải bản chép nguyên xi output của `javap`. Các chỉ số constant pool, cách in tên annotation và thứ tự hiển thị có thể khác theo JDK/compiler.

Kết quả có ý nghĩa:

- `@ClassHint`: đã được biên dịch vào class file, ở thuộc tính **`RuntimeInvisibleAnnotations`**.
- `@DefaultHint`: cũng ở thuộc tính **`RuntimeInvisibleAnnotations`** vì không khai báo `@Retention`.
- `@RuntimeHint`: ở thuộc tính **`RuntimeVisibleAnnotations`**.
- `@SourceHint`: không có entry annotation tương ứng trong `TaggedService.class`, vì nó có retention `SOURCE`.

Đừng suy luận từ chữ “Runtime” trong tên thuộc tính rằng Java Reflection sẽ nhìn thấy mọi metadata ở đó. `RuntimeInvisibleAnnotations` là tên chính thức của **thuộc tính class-file lưu các annotation không hiển thị tại runtime qua Reflection chuẩn**. Ngược lại, `RuntimeVisibleAnnotations` chứa những annotation runtime-visible mà Reflection có thể trả về theo các quy tắc của API.

Để đối chiếu thêm, thử:

```bash
javap -v -p ClassHint
```

Lệnh này đang kiểm tra **`ClassHint.class`**, tức định nghĩa annotation type. Nó có thể hiển thị chính meta-annotation `@Retention(CLASS)` với thuộc tính runtime-visible của **`@Retention`**. Đừng nhầm thông tin trên định nghĩa `ClassHint` với lần sử dụng `@ClassHint` trên `TaggedService`.

### Vì sao gọi là RuntimeInvisibleAnnotations?

Định dạng class file phân biệt hai nhóm annotation trên declaration:

- `RuntimeVisibleAnnotations`: VM phải lưu/hiển thị phù hợp để các API runtime reflection có thể truy cập theo cơ chế được định nghĩa.
- `RuntimeInvisibleAnnotations`: thông tin nằm trong class file nhưng không được VM buộc phải cung cấp cho Reflection chuẩn.

Khi annotation gắn lên **tham số phương thức** hoặc **vị trí sử dụng kiểu** (type-use), class file có những thuộc tính chuyên biệt tương ứng, chẳng hạn `RuntimeInvisibleParameterAnnotations` hoặc `RuntimeInvisibleTypeAnnotations`. Chúng tuân theo cùng ý tưởng về **visibility theo retention**, nhưng không phải mọi annotation đều nằm trong thuộc tính declaration `RuntimeInvisibleAnnotations`.

Vì vậy, khi kiểm tra bytecode, chọn đúng lớp và đúng loại vị trí được đánh annotation. Ví dụ chính ở trên gắn annotation lên **class declaration** nên dùng `RuntimeInvisibleAnnotations` và `RuntimeVisibleAnnotations`.

## 5. Vì sao Reflection không đọc được metadata CLASS?

Java Reflection làm việc thông qua các biểu diễn runtime như `Class`, `Method`, `Field`, `Constructor` và `Parameter`. Những API đọc annotation của Reflection theo hợp đồng của ngôn ngữ/API được thiết kế cho các annotation có **`RetentionPolicy.RUNTIME`**.

Những lời gọi như sau không mở file `.class` để tự giải mã mọi thuộc tính của định dạng class file:

```java
TaggedService.class.getAnnotation(ClassHint.class);           // null
TaggedService.class.getDeclaredAnnotation(ClassHint.class);   // null
TaggedService.class.isAnnotationPresent(ClassHint.class);     // false
```

Các dòng là **đoạn minh họa đặt trong một phương thức/khối lệnh**, sử dụng kiểu từ ví dụ 3.

Việc đổi từ `getAnnotation` sang `getDeclaredAnnotation` hoặc `getAnnotationsByType` **không phải mẹo để lấy được annotation `CLASS`**. Các API đó khác nhau chủ yếu ở cách xét annotation khai báo trực tiếp, thừa kế hoặc lặp hợp lệ; chúng vẫn tuân thủ runtime visibility.

Nếu phải truy cập `ClassHint` sau compile, công cụ cần làm việc với **cấu trúc class file** (ví dụ một bytecode reader), chứ không thể chỉ đổi sang một method khác của `Class<?>`.

### Tránh nhầm “JVM không lưu” với “Reflection không trả”

`RetentionPolicy.CLASS` quy định metadata **có mặt trong class file được biên dịch**. Khi JVM nạp class file, nó không được yêu cầu phải trình bày metadata đó cho Java Reflection. Cách VM lưu trữ nội bộ khi đã nạp class là một chi tiết triển khai; không nên suy ra một bảo đảm rằng dữ liệu `CLASS` có thể truy vấn qua API Reflection.

Nói chính xác:

> `CLASS` là chính sách **lưu thông tin trong class file**; **không có khả năng đọc qua Reflection chuẩn**, và không có một hành vi nghiệp vụ nào tự chạy chỉ vì metadata còn tồn tại.

## 6. Ai có thể khai thác annotation CLASS?

Các bên tiêu thụ khác nhau đọc annotation vào những thời điểm khác nhau:

| Thời điểm | Cách đọc | Có thể khai thác CLASS? | Ghi chú |
| --- | --- | --- | --- |
| Khi biên dịch source | Compiler hoặc annotation processor làm việc trên model phần tử | Có | Processor được cấu hình có thể thấy annotation trên source tại compile-time |
| Sau biên dịch, trước khi chạy | Công cụ phân tích hoặc biến đổi `.class` | Có | Có thể đọc `RuntimeInvisibleAnnotations` từ bytecode |
| Khi khởi động/chạy, nhưng công cụ tự đọc bytes của class file | Bytecode reader được ứng dụng/framework dùng | Có, nếu metadata vẫn còn trong bytes | Đây là **đọc class file**, không phải Java Reflection chuẩn |
| Khi chạy, dùng `Class.getAnnotation(...)` | Java Reflection | **Không** | API tiêu chuẩn chỉ thấy annotation thích hợp với `RUNTIME` |

**Ví dụ tình huống:** một build tool quét class file để lập danh mục thành phần được đánh `@BuildHint`, hoặc một công cụ bytecode đọc annotation để thực hiện biến đổi. Công cụ đó có thể sử dụng thông tin `CLASS` mà không cần tạo instance từ lớp được đánh dấu.

Một annotation `CLASS` không tự động bắt buộc compiler chạy processor, không tự động tạo source mới và không tự động yêu cầu framework quét class file. **Consumer phải được cài đặt và kích hoạt cụ thể**.

### Reflection và công cụ đọc bytecode trong cùng một ứng dụng

Một framework ở runtime **có thể** chọn quét bytecode trực tiếp, nhận metadata `CLASS` rồi cấu hình một hành vi. Điều này không mâu thuẫn với câu “Reflection chuẩn không đọc được”. Cùng diễn ra ở runtime nhưng **hai con đường truy cập metadata khác nhau**.

Khi đọc tài liệu framework, cần phân biệt rõ framework dùng **Reflection** hay **class-file metadata reader**. Chỉ từ thông tin “framework chạy lúc khởi động” thì chưa thể suy ra nó dùng cơ chế nào.

## 7. CLASS có phải lựa chọn tốt hơn RUNTIME trong mọi trường hợp?

Không. Chọn retention theo **nhu cầu của consumer**.

Chọn `CLASS` khi metadata chủ yếu dành cho công cụ đọc class file, bytecode instrumentation, kiểm tra build hoặc một pipeline cần dữ liệu trong binary nhưng không cần Reflection.

Chọn `RUNTIME` nếu **chương trình dự kiến đọc annotation qua Java Reflection**. Ví dụ một ứng dụng viết:

```java
if (componentClass.isAnnotationPresent(ServiceMarker.class)) {
    // Chủ động đăng ký component theo metadata.
}
```

Nếu `ServiceMarker` có retention `CLASS`, điều kiện này sẽ là `false` do không thấy annotation, kể cả source có `@ServiceMarker`. Nếu muốn kiểm tra bằng Reflection, cần chọn retention `RUNTIME` cho `ServiceMarker`.

Chọn `SOURCE` nếu annotation chỉ cần dùng ở compile-time và không cần mang theo sang class file.

| Nhu cầu cụ thể | Retention đề xuất |
| --- | --- |
| Annotation processor kiểm tra quy ước source, không cần dữ liệu ở `.class` | `SOURCE` thường đủ |
| Công cụ sau compile quét `.class` để kiểm tra/biến đổi | `CLASS` |
| Mã Java gọi `getAnnotation` khi chạy | `RUNTIME` |
| Cần cả bytecode tooling lẫn Reflection | `RUNTIME` |
| Chưa biết consumer là ai | Xác định consumer và cách đọc trước khi chọn |

Giữ metadata nhiều giai đoạn hơn có thể tăng lượng thông tin được mang theo trong artifact. Tuy nhiên **`CLASS` không phải cơ chế bảo mật hay bí mật**: dữ liệu được ghi trong `.class`, nên người có class file và công cụ phù hợp có thể xem được. Không đặt khóa bí mật, mật khẩu hoặc token vào giá trị annotation với suy nghĩ rằng Reflection không đọc được thì dữ liệu sẽ an toàn.

## 8. Hai khái niệm độc lập: retention và target

Một annotation thường có cả:

```java
@Retention(RetentionPolicy.CLASS)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface BuildHint {
    String value();
}
```

- `@Retention(CLASS)`: **metadata được giữ bao lâu và Reflection có thấy hay không**.
- `@Target({TYPE, METHOD})`: **annotation được phép gắn ở những loại vị trí nào**.

`TYPE` bao gồm các khai báo kiểu thích hợp; `METHOD` là phương thức. Nếu cần đánh dấu parameter, dùng `ElementType.PARAMETER`; nếu cần vị trí dùng kiểu, dùng `ElementType.TYPE_USE`. Target ảnh hưởng vị trí hợp lệ và dạng class-file attribute tương ứng, **không làm thay đổi chính sách retention**.

Một annotation có target `TYPE` và retention `CLASS` vẫn **không tự xuất hiện qua Reflection** chỉ vì nó đặt trên class. Ngược lại, annotation có target `METHOD` và retention `RUNTIME` có thể được đọc từ đúng đối tượng `Method` bằng Reflection, nếu chương trình tìm đúng phương thức.

## 9. Điều gì xảy ra khi có @Inherited?

`@Inherited` là một meta-annotation quy định cách **Reflection truy vấn annotation class có retention `RUNTIME`** trên subclass trong trường hợp cụ thể. Nó không tự nâng `CLASS` lên thành `RUNTIME`.

Ví dụ minh họa chính sách:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.CLASS)
@interface Marker {
}

@Marker
class Parent {
}

class Child extends Parent {
}
```

Dù dùng `@Inherited`, `Child.class.getAnnotation(Marker.class)` vẫn không lấy được `Marker`. Bản thân `Marker` có retention `CLASS`, nên Reflection không cung cấp annotation này trên `Parent`, và quy tắc thừa kế không thể làm nó hiện ra.

`@Inherited` chỉ áp dụng cho truy vấn annotation trên **class và quan hệ kế thừa lớp phù hợp**, không phải cơ chế khiến mọi annotation từ interface/method/field tự được kế thừa. Đây là khía cạnh độc lập với lựa chọn lưu giữ metadata.

## 10. Những điểm có thể làm metadata CLASS biến mất khỏi artifact phát hành

Một `javac` thông thường với `RetentionPolicy.CLASS` ghi annotation theo hợp đồng ngôn ngữ/class file. Tuy nhiên, nếu bạn kiểm tra artifact cuối cùng trong một pipeline nhiều bước, phải biết class file có thể được xử lý tiếp:

1. **Bytecode weaving/instrumentation:** công cụ đọc, chỉnh và ghi lại class file; tùy cấu hình, dữ liệu annotation có thể được giữ hoặc thay đổi.
2. **Shrinking/obfuscation:** công cụ rút gọn hoặc biến đổi có thể loại bỏ những thuộc tính không được yêu cầu giữ.
3. **Thay thế class file:** nếu runtime đang nạp một artifact/build khác với bản `javap` được kiểm tra, kết quả không phản ánh cùng binary.
4. **Chỉ kiểm tra sai class:** annotation trên phương thức/tham số/type-use có thể nằm trong attribute khác, không nằm ở phần top-level declaration của class.

Do đó, khi người dùng báo “`@Retention(CLASS)` mà tool không tìm thấy”, hãy kiểm tra **đúng file `.class` đầu ra của build**, chính sách retention, đúng vị trí annotation và cấu hình công cụ biến đổi. Điều này khác với trường hợp Reflection trả `null`: khi dùng Reflection với `CLASS`, `null` là hành vi được mong đợi.

## 11. Các lỗi hiểu sai thường gặp

**“CLASS nghĩa là chỉ còn annotation trên kiểu `Class<?>`.”** Sai. Tên `CLASS` ở đây là **giai đoạn lưu giữ dữ liệu**, không phải `java.lang.Class` hay `ElementType.TYPE`.

**“Annotation đã được lưu trong .class thì `Class.getAnnotation` chắc chắn đọc được.”** Sai. Reflection có hợp đồng runtime visibility riêng. Metadata `CLASS` có thể đọc bằng công cụ xử lý class file.

**“Không ghi `@Retention` thì mặc định `RUNTIME`.”** Sai. Mặc định là `CLASS`. Đây là lý do nhiều annotation tự viết không hiện ra khi truy vấn bằng Reflection.

**“`@Inherited` giúp Reflection đọc được CLASS annotation.”** Sai. `@Inherited` không ghi đè retention.

**“`RuntimeInvisibleAnnotations` nghĩa là class file không chứa annotation.”** Sai. Đây chính là một thuộc tính **chứa** annotation, nhưng không hiển thị cho Reflection chuẩn.

**“`@Retention(RUNTIME)` sẽ tự thực thi logic của annotation.”** Sai. Dù dữ liệu có thể đọc được, phải có code hoặc framework chủ động truy vấn và xử lý.

**“Annotation CLASS là bí mật vì không đọc qua Reflection.”** Sai. Người có class file có thể phân tích bytecode và thấy metadata.

**“Chạy một framework ở runtime tức là nó chỉ có thể đọc bằng Reflection.”** Sai. Framework có thể tự đọc bytes của class file; cần xem cơ chế cụ thể, không đoán từ thời điểm chạy.

## 12. Tự kiểm tra

### Câu 1: Đọc kết quả

Với ví dụ `ClassRetentionDemo` ở mục 3, tại sao `type.getDeclaredAnnotation(ClassHint.class)` trả `null` nhưng `javap -v -p TaggedService` vẫn có thể hiển thị `ClassHint`?

**Gợi ý:** hai cách đọc dùng hai lớp API khác nhau: Reflection runtime và bộ đọc class file.

### Câu 2: Retention mặc định

Nếu bỏ toàn bộ `@Retention` trên một annotation type tự định nghĩa, nó sẽ mang chính sách nào? Có thể gọi `getAnnotation` để đọc lần sử dụng annotation đó trên class không?

**Đáp án:** `CLASS`; lần sử dụng không hiện qua Reflection chuẩn.

### Câu 3: Chọn thiết kế

Công cụ A kiểm tra metadata sau biên dịch bằng cách đọc trực tiếp `.class`. Chương trình B gọi `SomeClass.class.getAnnotation(Flag.class)` khi chạy. Nếu cùng dùng `@Flag`, retention nào đáp ứng cả hai?

**Đáp án:** `RUNTIME`, vì class file vẫn chứa metadata và Reflection cũng cần nhìn thấy nó.

### Câu 4: Phân tích thuộc tính bytecode

Giả sử `@Hint` gắn trực tiếp lên một class, có `@Retention(CLASS)`. Trong output `javap -v` của **class đó**, nên tìm `RuntimeInvisibleAnnotations` hay `RuntimeVisibleAnnotations`?

**Đáp án:** `RuntimeInvisibleAnnotations`. Với annotation ở vị trí khác như parameter/type-use, phải tra thuộc tính chuyên biệt tương ứng.

### Câu 5: Meta-annotation của chính annotation type

Tại sao `ClassHint.class.getAnnotation(Retention.class).value()` có thể trả `CLASS` dù `TaggedService.class.getAnnotation(ClassHint.class)` trả `null`?

**Đáp án:** truy vấn thứ nhất đọc `@Retention` **trên định nghĩa `ClassHint`**, truy vấn thứ hai đọc **lần sử dụng `@ClassHint` trên `TaggedService`**. Hai annotation được truy vấn là hai đối tượng metadata khác nhau với chính sách retention khác nhau.

### Câu 6: Một lỗi thực tế

Bạn dùng `@Retention(CLASS)` cho `@AutoRegister`, rồi viết code runtime:

```java
if (MyComponent.class.isAnnotationPresent(AutoRegister.class)) {
    register(MyComponent.class);
}
```

Tại sao phương thức `register` không được gọi chỉ dựa vào annotation đó? Nếu muốn tiếp tục dùng Reflection, cần thay đổi điều gì?

**Đáp án:** `isAnnotationPresent` là Reflection và không thấy annotation `CLASS`. Nếu muốn nhận diện theo Reflection, `@AutoRegister` phải có retention `RUNTIME` (và chương trình vẫn cần chủ động gọi logic đăng ký). Một lựa chọn khác là thiết kế cơ chế đọc metadata trực tiếp từ bytecode, nhưng đó là hướng xử lý khác.

## 13. Checklist khi thiết kế hoặc debug CLASS retention

1. **Ai là consumer?** Compiler/annotation processor, bytecode tool hay Reflection?
2. **Thời điểm đọc?** Trong lúc compile source, sau compile, hay khi chương trình chạy?
3. **Annotation type khai báo retention gì?** Nếu không khai báo, nhớ `CLASS` là mặc định.
4. **Đang kiểm tra đúng class file chưa?** Với class declaration, tìm đúng thuộc tính `RuntimeInvisibleAnnotations` trong file lớp được đánh dấu.
5. **Có công cụ biến đổi artifact không?** Kiểm tra binary cuối cùng được tool hoặc JVM thực sự sử dụng.
6. **Có nhầm việc truy vấn `@Retention` trên kiểu annotation với truy vấn lần sử dụng annotation đó không?**
7. **Có mong Reflection đọc được `CLASS` không?** Nếu có, xem lại yêu cầu và chọn `RUNTIME` hoặc đổi cách đọc.
8. **Có thực sự triển khai consumer?** Annotation tự thân là metadata; nó không tự bật chức năng ứng dụng.

Kết luận về `RetentionPolicy.CLASS` rất cụ thể: **annotation được bảo lưu trong class file để những công cụ cần bytecode có thể khai thác, đồng thời không xuất hiện qua Java Reflection chuẩn khi chạy**. Nắm rõ ranh giới này giúp chọn retention phù hợp và tránh các lỗi `getAnnotation(...) == null` khó hiểu khi thiết kế annotation tự định nghĩa.