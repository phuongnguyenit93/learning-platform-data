# RuntimeVisibleAnnotations và RuntimeInvisibleAnnotations trong Java class file

## 1. Hai thuộc tính này là gì?

Khi `javac` biên dịch một chương trình có annotation, thông tin annotation có thể trở thành **metadata trong tệp `.class`**. Theo định dạng Java Virtual Machine (JVM) class file, hai thuộc tính (*attributes*) quan trọng đối với annotation trên khai báo là:

- **`RuntimeVisibleAnnotations`**: lưu các annotation mà Java runtime cần hỗ trợ truy xuất bằng Reflection API, điển hình là annotation type có `@Retention(RetentionPolicy.RUNTIME)`.
- **`RuntimeInvisibleAnnotations`**: lưu các annotation được giữ trong class file nhưng **không được Java reflection thông thường cung cấp tại runtime**, điển hình là annotation type có `@Retention(RetentionPolicy.CLASS)`.

Từ **visible/invisible** ở đây nói về **mức hỗ trợ của runtime reflection**, không phải `public`/`private`, không phải việc class có được JVM tải hay không, và cũng không phải khả năng một công cụ đọc bytecode có thể nhìn thấy dữ liệu.

Một công cụ đọc class file như `javap -v` hoặc thư viện phân tích bytecode có thể nhìn thấy **cả hai loại thuộc tính**. Nhưng khi dùng `Class.getAnnotation(...)`, `Field.getAnnotation(...)` hoặc `Method.getAnnotation(...)`, các annotation với retention `CLASS` không được cung cấp bởi những API này.

Ví dụ, nếu một class có:

```java
@ClassStamp("saved-in-bytecode")
@RuntimeStamp("read-by-reflection")
class Report {}
```

và hai annotation type tương ứng được định nghĩa với retention `CLASS`, `RUNTIME`, thì trong metadata class có thể thấy:

```text
RuntimeInvisibleAnnotations:
  ClassStamp(value="saved-in-bytecode")

RuntimeVisibleAnnotations:
  RuntimeStamp(value="read-by-reflection")
```

Khối trên là **sơ đồ giản lược**, không phải bản sao đầu ra `javap`: lệnh `javap -v` còn hiển thị các chỉ số constant pool và cấu trúc khác. Phần ví dụ chạy được ở mục 4 sẽ cho thấy nội dung thật của các thuộc tính này.

## 2. Tương ứng với ba mức @Retention

`@Retention` là meta-annotation quyết định compiler giữ annotation đến giai đoạn nào. Nó được khai báo trên **annotation type**, không phải trên từng lần gắn annotation.

| `RetentionPolicy` | Annotation trên class/field/method trong source | Còn trong class file sau biên dịch? | Thuộc tính class file dành cho annotation khai báo | Reflection lúc chạy |
| --- | --- | --- | --- | --- |
| `SOURCE` | Có | Không | Không tạo entry tương ứng cho lần dùng annotation đó | Không |
| `CLASS` | Có | Có | `RuntimeInvisibleAnnotations` | Không |
| `RUNTIME` | Có | Có | `RuntimeVisibleAnnotations` | Có, theo đúng vị trí và quy tắc tra cứu |

Một ví dụ định nghĩa annotation:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceStamp {}

@Retention(RetentionPolicy.CLASS)
@interface ClassStamp {}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeStamp {}
```

Đây là các **khai báo hỗ trợ**; chưa phải chương trình độc lập. Java mặc định retention là **`CLASS`** khi annotation type không khai báo `@Retention`.

Những điểm đặc biệt quan trọng:

1. `SOURCE` không được ghi như annotation của **phần tử được gắn** vào class file. Tuy nhiên, compiler vẫn tạo tệp `SourceStamp.class` cho **định nghĩa annotation type** `SourceStamp` nếu type đó được biên dịch, và `SourceStamp.class` vẫn có thể chứa các meta-annotation mô tả chính type ấy. Đừng nhầm hai đối tượng kiểm tra này.
2. `CLASS` vẫn để lại dấu vết trong bytecode. Nói rằng “annotation `CLASS` biến mất sau biên dịch” là sai; đúng hơn là nó không có mặt trong reflection API runtime thông thường.
3. `RUNTIME` được giữ ở class file và làm metadata sẵn có cho reflection. Điều này **không** tự động thực thi logic nghiệp vụ.
4. `@Retention` độc lập với `@Target`. `@Target` quyết định có thể gắn annotation vào class, field, method, constructor hay type-use; `@Retention` quyết định annotation được giữ đến đâu.
5. `@Documented` ảnh hưởng việc hiển thị trong tài liệu Javadoc phù hợp; `@Inherited` ảnh hưởng một số quy tắc tra cứu trên class. Chúng **không biến** `CLASS` thành `RUNTIME`.

## 3. RuntimeVisibleAnnotations nằm ở đâu trong class file?

Một tệp `.class` có nhiều cấu trúc, gồm thông tin về class, các trường (*field_info*), các phương thức (*method_info*) và các thuộc tính (*attributes*). Attribute dành cho annotation khai báo có thể được gắn vào những phần tử tương ứng trong class file.

Ví dụ một class:

```java
@RuntimeStamp("type")
class Sample {
    @RuntimeStamp("field")
    int count;

    @RuntimeStamp("method")
    void run() {}
}
```

Nếu `RuntimeStamp` là annotation type có retention `RUNTIME` và target phù hợp, compiler có thể phát ra:

- Một `RuntimeVisibleAnnotations` tại **cấp class** chứa metadata `@RuntimeStamp("type")`.
- Một `RuntimeVisibleAnnotations` trong metadata của **field `count`** chứa `@RuntimeStamp("field")`.
- Một `RuntimeVisibleAnnotations` trong metadata của **method `run`** chứa `@RuntimeStamp("method")`.

Đây là các vị trí **khác nhau**. Reflection trên `Sample.class` không tự trả annotation gắn riêng cho field hoặc method; cần lấy `Field`/`Method` rồi gọi API trên đúng đối tượng đó.

`RuntimeInvisibleAnnotations` có cách phân bố tương tự đối với annotation có retention `CLASS`. `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations` cũng có thể cùng xuất hiện trên **một phần tử**, vì cùng class có thể mang nhiều annotation với các chính sách retention khác nhau.

Tên attribute trong `javap` có thể xuất hiện nhiều lần: một lần ở đoạn field, một lần ở method và một lần tại cấp class. Muốn diễn giải đúng, phải xem attribute nằm trong **ngữ cảnh khai báo nào**, không chỉ tìm thấy chuỗi `RuntimeVisibleAnnotations` trong đầu ra.

## 4. Ví dụ Java 17+ hoàn chỉnh: từ source sang javap và reflection

Ta viết một chương trình có ba annotation tương ứng với `SOURCE`, `CLASS` và `RUNTIME`, gắn lên **class, field và method**. Sau khi biên dịch, dùng `javap -v` quan sát metadata và dùng reflection để xác nhận điều gì thực sự đọc được ở runtime.

Lưu nguyên khối mã sau thành tệp **`RetentionAttributesDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.SOURCE)
@interface SourceStamp {
    String value();
}

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.CLASS)
@interface ClassStamp {
    String value();
}

@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeStamp {
    String value();
}

@SourceStamp("source-type")
@ClassStamp("class-type")
@RuntimeStamp("runtime-type")
class Report {
    @SourceStamp("source-field")
    @ClassStamp("class-field")
    @RuntimeStamp("runtime-field")
    private int total;

    @SourceStamp("source-method")
    @ClassStamp("class-method")
    @RuntimeStamp("runtime-method")
    public int count() {
        return total;
    }
}

public class RetentionAttributesDemo {
    public static void main(String[] args)
            throws NoSuchFieldException, NoSuchMethodException {
        Class<Report> type = Report.class;
        Field field = type.getDeclaredField("total");
        Method method = type.getDeclaredMethod("count");

        System.out.println("SOURCE on class: "
                + type.isAnnotationPresent(SourceStamp.class));
        System.out.println("CLASS on class: "
                + type.isAnnotationPresent(ClassStamp.class));
        System.out.println("RUNTIME on class: "
                + type.getAnnotation(RuntimeStamp.class).value());
        System.out.println("RUNTIME on field: "
                + field.getAnnotation(RuntimeStamp.class).value());
        System.out.println("RUNTIME on method: "
                + method.getAnnotation(RuntimeStamp.class).value());
    }
}
```

### 4.1. Biên dịch và chạy

Từ thư mục chứa `RetentionAttributesDemo.java`, dùng JDK 17 trở lên:

```bash
javac --release 17 -d out RetentionAttributesDemo.java
java -cp out RetentionAttributesDemo
```

**Stdout chính xác:**

```text
SOURCE on class: false
CLASS on class: false
RUNTIME on class: runtime-type
RUNTIME on field: runtime-field
RUNTIME on method: runtime-method
```

Giải thích từng kết quả:

- `SOURCE on class: false`: compiler không giữ `@SourceStamp("source-type")` như runtime annotation trên `Report`.
- `CLASS on class: false`: `@ClassStamp("class-type")` có thể **vẫn có trong class file**, nhưng `isAnnotationPresent` không nhìn thấy retention `CLASS`.
- `RUNTIME on class: runtime-type`: annotation type `RuntimeStamp` cho phép runtime reflection quan sát, nên `getAnnotation(RuntimeStamp.class)` lấy được giá trị trên class.
- Hai dòng còn lại: dùng đúng đối tượng `Field` và `Method` để đọc annotation runtime trên các member được đánh dấu.

Kết quả này đã được kiểm chứng bằng biên dịch với `javac --release 17` và chạy trên JDK hỗ trợ Java 17.

### 4.2. Quan sát bằng javap -v

Sau khi biên dịch, chạy:

```bash
javap -v -p -classpath out Report
```

- `-v` (verbose) cho biết cấu trúc class file, constant pool và các thuộc tính.
- `-p` hiển thị cả các member không public, vì field `total` là `private`.
- `-classpath out` cho `javap` biết nơi tìm `Report.class`.

Trong đầu ra, bạn sẽ gặp những đoạn có hình dạng tương tự dưới đây (đã **bỏ chỉ số constant pool và các dòng không liên quan**):

```text
private int total;
  ...
  RuntimeVisibleAnnotations:
    RuntimeStamp(value="runtime-field")
  RuntimeInvisibleAnnotations:
    ClassStamp(value="class-field")

public int count();
  ...
  RuntimeVisibleAnnotations:
    RuntimeStamp(value="runtime-method")
  RuntimeInvisibleAnnotations:
    ClassStamp(value="class-method")

...
RuntimeVisibleAnnotations:
  RuntimeStamp(value="runtime-type")
RuntimeInvisibleAnnotations:
  ClassStamp(value="class-type")
```

Đây là **mẫu diễn giải**, không phải stdout nguyên bản của `javap`; bản thực tế có số tham chiếu như `#14`, định dạng nhiều dòng, flags, descriptors và các phần khác. Nội dung thực tế đã được đối chiếu với `javap -v -p` sau khi biên dịch ví dụ.

Điều đáng chú ý:

1. `RuntimeStamp` xuất hiện trong `RuntimeVisibleAnnotations` trên class, field và method, tương ứng retention `RUNTIME`.
2. `ClassStamp` xuất hiện trong `RuntimeInvisibleAnnotations` ở ba vị trí, tương ứng retention `CLASS`.
3. Các lần dùng `@SourceStamp(...)` trên `Report` **không xuất hiện** trong các annotation attributes này vì retention `SOURCE`.
4. Tên `Report` ở lệnh `javap` rất quan trọng. Nếu thay bằng `RuntimeStamp`, bạn đang phân tích **class file của annotation type** thay vì class được gắn annotation, nên có thể thấy các meta-annotation như `@Retention`, `@Target` — đó là dữ liệu khác.

### 4.3. Trường hợp dùng Java reflection để đọc CLASS retention

Đừng viết:

```java
ClassStamp stamp = Report.class.getAnnotation(ClassStamp.class);
System.out.println(stamp.value());
```

Đây là đoạn **minh họa không độc lập** và có thể ném `NullPointerException`, bởi `getAnnotation(ClassStamp.class)` trả `null` đối với annotation chỉ có retention `CLASS`.

Muốn đọc `ClassStamp` ở runtime bằng dữ liệu class file, cần **công cụ đọc bytecode**, không phải `AnnotatedElement.getAnnotation` thông thường. Thư viện phân tích bytecode có thể đọc `RuntimeInvisibleAnnotations` mà không cần instance của `Report`. Còn nếu bạn kiểm soát định nghĩa annotation và mục tiêu thật sự là reflection lúc chạy, cân nhắc thay retention thành `RUNTIME` rồi **biên dịch lại** những class đã gắn annotation.

## 5. RuntimeInvisible không có nghĩa private, bị xóa hoặc không đọc được bằng mọi công cụ

Các cách hiểu sai dễ dẫn tới thiết kế sai:

**Sai 1: “Invisible nghĩa là annotation được khai báo private.”** Retention khác access modifier. Một annotation type `public` vẫn có thể được lưu vào `RuntimeInvisibleAnnotations` khi nó có retention `CLASS`.

**Sai 2: “Invisible nghĩa là metadata đã bị loại khỏi tệp .class.”** Không. Chính attribute này là **dấu vết** metadata trong class file. Các công cụ đọc bytecode có thể phân tích nó mà không dựa vào reflection API.

**Sai 3: “Visible là vì class được khởi tạo bằng new.”** Không. `RuntimeVisibleAnnotations` là metadata trên class file. Bạn có thể dùng `Report.class.getAnnotation(RuntimeStamp.class)` mà không tạo bất kỳ instance `Report` nào. Số lượng object được tạo/GC không quyết định retention.

**Sai 4: “Nếu `getAnnotation` trả null thì class file không chứa annotation.”** Không đủ. Có thể annotation có retention `CLASS`; có thể đang đọc sai class/member; cũng có thể là repeatable annotation được biểu diễn qua container. Muốn chẩn đoán, xác định định nghĩa annotation, target, retention và dùng `javap -v` khi cần.

**Sai 5: “Đổi @Retention là mọi bytecode cũ tự cập nhật.”** Không. Tệp `.class` đã biên dịch giữ metadata theo lúc biên dịch. Sau khi sửa định nghĩa annotation type, phải tái biên dịch những nguồn áp dụng annotation nếu muốn có các attribute mới phù hợp. Đừng mặc nhiên tin rằng chỉ thay JAR chứa annotation type sẽ viết lại những class file đã tồn tại.

## 6. Đừng nhầm với RuntimeVisibleTypeAnnotations / RuntimeInvisibleTypeAnnotations

Hai thuộc tính ở tiêu đề bài học chủ yếu áp dụng cho **annotation trên khai báo** (*declaration annotations*). Với annotation đặt trên **vị trí sử dụng kiểu** (*type-use annotations*, Java 8+), class file sử dụng những tên khác:

- `RuntimeVisibleTypeAnnotations` cho type-use annotations có retention `RUNTIME`.
- `RuntimeInvisibleTypeAnnotations` cho type-use annotations có retention `CLASS`.

Ví dụ minh họa (không phải chương trình độc lập):

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonEmptyText {}

class Repository {
    List<@NonEmptyText String> labels;
}
```

`@NonEmptyText` chú thích **đối số kiểu `String`** của `List<String>`, không phải toàn bộ khai báo field `labels`. Metadata phù hợp thuộc nhóm *type annotations*, không phải chỉ `RuntimeVisibleAnnotations` thông thường.

Đọc thông tin này cần đi qua API type annotation, ví dụ `Field.getAnnotatedType()`, rồi `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` để truy xuất annotation trên đối số kiểu. Không nên mong `field.getAnnotation(NonEmptyText.class)` tự tìm thấy mọi annotation trong cấu trúc kiểu của field.

Một annotation type có thể có nhiều target nên trong một số trường hợp compiler có thể sinh metadata ở nhiều vị trí khác nhau, tùy chú thích áp dụng lên declaration hay type-use. Muốn kết luận, xác định **target và vị trí chính xác trong cú pháp Java** rồi đọc attribute tương ứng.

## 7. Annotation trên tham số và giá trị mặc định: tên attribute khác nữa

### 7.1. Method/constructor parameter annotations

Annotation trên **khai báo tham số** (`ElementType.PARAMETER`) có thể được lưu trong:

- `RuntimeVisibleParameterAnnotations` nếu retention là `RUNTIME`;
- `RuntimeInvisibleParameterAnnotations` nếu retention là `CLASS`.

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface RequestId {}

class Api {
    void receive(@RequestId String id) {}
}
```

Đoạn trên là **minh họa**, muốn biên dịch độc lập cần import `Retention`, `RetentionPolicy`, `Target` và `ElementType` phù hợp. Để truy vấn ở runtime, có thể lấy `Method` rồi gọi `getParameterAnnotations()` hoặc dùng các đối tượng `Parameter`.

Lưu ý rằng **annotation trên parameter declaration** và annotation trên **type-use bên trong kiểu tham số** là hai loại vị trí khác nhau. Chúng có thể được lưu bằng các họ attribute riêng.

### 7.2. AnnotationDefault

Nếu annotation type khai báo một element có giá trị mặc định:

```java
@interface Priority {
    int value() default 5;
}
```

Giá trị `default 5` được lưu bằng attribute **`AnnotationDefault`** tại method tương ứng của **annotation type** `Priority`. Đó không phải một lần sử dụng `@Priority` trên class và cũng không phải `RuntimeVisibleAnnotations`. API `Method.getDefaultValue()` trên method element phản chiếu cho biết default nếu có.

Đừng nhầm `AnnotationDefault` với retention của annotation type. Một annotation có default và retention `CLASS` vẫn là một kiểu annotation có element mặc định, nhưng việc dùng annotation ấy trên class không vì thế trở thành visible qua runtime reflection.

## 8. Annotation lặp (@Repeatable) và container

Khi cùng một repeatable annotation được gắn nhiều lần vào class hoặc member, compiler biểu diễn các annotation thành phần qua **container annotation type** được xác định bởi `@Repeatable`.

Ví dụ:

```java
@Role("READ")
@Role("WRITE")
class AccessService {}
```

Đây là **minh họa**; giả định `Role` là repeatable và có container phù hợp, cả hai có retention `RUNTIME`. Trong class file, dữ liệu có thể hiện diện dưới dạng annotation container trong `RuntimeVisibleAnnotations`. API `getAnnotation(Role.class)` không tự mở container, nhưng `getAnnotationsByType(Role.class)` có thể trả các `Role` thành phần.

Như vậy, khi thấy `RuntimeVisibleAnnotations` trong `javap -v` nhưng `getAnnotation(Role.class)` trả `null`, ngoài retention còn cần kiểm tra **cách biểu diễn repeatable/container**.

Nếu dùng một container với retention `CLASS` thì metadata tương ứng không được Java reflection runtime đọc qua những API này. Các ràng buộc tương thích giữa repeatable annotation và container cần được Java compiler kiểm tra ở thời điểm định nghĩa.

## 9. Liên hệ với reflection, annotation processor và bytecode tools

Có ba con đường đọc annotation, và không nên đánh đồng chúng.

| Cơ chế | Thời điểm | SOURCE | CLASS | RUNTIME |
| --- | --- | --- | --- | --- |
| **Compiler / annotation processor** khi biên dịch nguồn | Compile time | Có thể đọc trong mô hình phần tử nguồn | Có thể đọc khi xử lý nguồn | Có thể đọc khi xử lý nguồn |
| **Phân tích `.class`**, ví dụ `javap -v` hoặc thư viện bytecode | Sau biên dịch | Không có lần dùng annotation `SOURCE` trong bytecode đích | Có thể đọc attribute invisible | Có thể đọc attribute visible |
| **Java Reflection API** trên metadata khai báo | Runtime | Không | Không | Có, nếu annotation tồn tại trên đúng đích và quan hệ tra cứu phù hợp |

Compiler có thể sử dụng `@Override` (retention `SOURCE`) để báo lỗi ngay lúc biên dịch mà không cần giữ nó trong class file. Công cụ kiểm tra bytecode có thể phân tích `CLASS` và `RUNTIME` sau biên dịch. Framework chạy dựa trên reflection thường cần annotation type có retention `RUNTIME`.

Nếu một chương trình build sử dụng **bytecode rewriting/obfuscation/shrinking**, các công cụ đó có thể biến đổi metadata. Khi gặp kết quả bất ngờ, ngoài source và retention phải kiểm tra **class file cuối cùng thực sự được nạp/phân phối**, không chỉ class file gốc ngay sau `javac`. Quy tắc giữ annotation của các công cụ bên thứ ba là phần cấu hình riêng, không phải ý nghĩa của hai attribute theo JVM Specification.

## 10. Quy trình chẩn đoán annotation “có trong source nhưng không đọc được”

Khi `getAnnotation(MyAnnotation.class)` trả `null`, làm theo thứ tự:

1. **Kiểm tra khai báo annotation type:** có `@Retention(RetentionPolicy.RUNTIME)` không? Nếu không có `@Retention` thì mặc định `CLASS`.
2. **Kiểm tra đúng target:** annotation được gắn lên class, field, method, constructor, parameter hay vị trí sử dụng kiểu? API reflection nào đọc đúng vị trí đó?
3. **Kiểm tra đúng phần tử:** `getDeclaredField("x")` khác `getDeclaredMethod("x")`; annotation trên method không phải annotation trên class.
4. **Xem class file:** `javap -v -p -classpath out FullyQualifiedClassName`. Tìm thuộc tính `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations` hoặc các biến thể `TypeAnnotations`/`ParameterAnnotations` thích hợp.
5. **Nhìn vào context của attribute:** nó thuộc class, field, method hay một thành phần khác? Không chỉ tìm thấy từ khóa rồi kết luận.
6. **Kiểm tra annotation lặp:** nếu type có `@Repeatable` và nhiều lần sử dụng, thử `getAnnotationsByType(T.class)`.
7. **Kiểm tra kế thừa:** `@Inherited` chỉ ảnh hưởng một số tra cứu annotation trên **class** theo superclass, không tự áp dụng tương tự cho field/method.
8. **Xác nhận class file đang chạy:** classpath, module path, bản JAR và công cụ biến đổi bytecode có thể khiến runtime dùng class khác bản bạn đang phân tích.
9. **Không sửa visibility của Java member một cách tùy tiện:** đọc metadata trên một private field bằng `Field.getAnnotation(...)` không đồng nghĩa phải gọi `setAccessible(true)`. Quyền đọc giá trị private field hoặc gọi private method là vấn đề khác.

## 11. Bài tập thực hành ngắn

Với chương trình `RetentionAttributesDemo.java` ở mục 4, bạn có thể tự kiểm chứng ba thay đổi:

**Bài tập A — đổi retention:** đổi `ClassStamp` từ `RetentionPolicy.CLASS` thành `RetentionPolicy.RUNTIME`; biên dịch lại chương trình; dự đoán `RuntimeInvisibleAnnotations` của các lần sử dụng `ClassStamp` sẽ chuyển sang nhóm `RuntimeVisibleAnnotations`, đồng thời `isAnnotationPresent(ClassStamp.class)` trên `Report.class` chuyển từ `false` sang `true`.

**Bài tập B — đổi vị trí:** bỏ `@RuntimeStamp("runtime-field")` khỏi field `total` nhưng giữ `@RuntimeStamp("runtime-type")` trên class. Sau khi biên dịch lại, `Report.class.getAnnotation(RuntimeStamp.class)` vẫn đọc được annotation trên class, còn `Field.getAnnotation(RuntimeStamp.class)` trên `total` sẽ không còn annotation đó. Khi thử, nhớ sửa code in field để kiểm tra `null` an toàn thay vì gọi `value()` ngay.

**Bài tập C — đọc đúng phần tử:** giữ nguyên chương trình, chạy `javap -v -p -classpath out Report` và chỉ ra ba vị trí `RuntimeVisibleAnnotations` tương ứng với class, field, method. Đối chiếu từng vị trí với ba giá trị `runtime-type`, `runtime-field` và `runtime-method`.

Các bài tập này không đòi hỏi thư viện ngoài JDK. Chúng giúp gắn kết ba cấp độ: **định nghĩa retention trong nguồn → attribute trong class file → kết quả đọc reflection**.

**Ghi nhớ:** `RuntimeVisibleAnnotations` chứa metadata annotation trên khai báo được runtime hỗ trợ đọc qua reflection, thường bắt nguồn từ `@Retention(RUNTIME)`. `RuntimeInvisibleAnnotations` chứa metadata còn trong bytecode nhưng không hiện qua reflection thông thường, thường bắt nguồn từ `@Retention(CLASS)`. `SOURCE` không để lại annotation entry tại đích sau biên dịch. Các type-use annotations, parameter annotations và element default có **họ attribute riêng**, nên cần chọn đúng attribute và API tra cứu trước khi kết luận dữ liệu đã tồn tại hay biến mất.
