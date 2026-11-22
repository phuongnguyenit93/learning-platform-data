# Khả năng xử lý SOURCE annotation và giới hạn khi annotation nằm trên kiểu sử dụng

## 1. Annotation SOURCE vẫn có thể được xử lý ở compile time

Trong Java, annotation type được khai báo bằng `@interface`. `@Retention` xác định annotation được giữ lại đến giai đoạn nào; nó **không** quyết định liệu compiler/annotation processor có thể đọc annotation khi đang xử lý mã nguồn hay không.

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface CompileCheck {
    String value();
}

@CompileCheck("domain")
class DomainService {}
```

Đây là đoạn minh họa cú pháp; không có `main`. Khi `javac` đang biên dịch `DomainService`, một annotation processor thích hợp **có thể tìm thấy** `@CompileCheck`, đọc phần tử `value()` và tạo chẩn đoán hoặc tệp sinh ra. Nhưng sau biên dịch, **lần sử dụng** `@CompileCheck("domain")` trên `DomainService` không được giữ trong `DomainService.class`, vì retention là `SOURCE`.

Đó không phải mâu thuẫn: **processor làm việc trên mô hình chương trình ở thời điểm biên dịch; reflection làm việc trên metadata còn lại ở runtime**.

| Retention của annotation | Processor khi biên dịch nguồn đang có annotation | Bytecode của phần tử được đánh dấu | Reflection thông thường lúc chạy |
| --- | --- | --- | --- |
| `SOURCE` | Có thể đọc trong mô hình compile-time phù hợp | Không lưu lần dùng annotation đó | Không đọc được |
| `CLASS` | Có thể đọc | Lưu, thường trong attribute runtime-invisible tương ứng | Không đọc được |
| `RUNTIME` | Có thể đọc | Lưu, thường trong attribute runtime-visible tương ứng | Có thể đọc nếu đúng vị trí/API |

Nếu một annotation type **không** khai báo `@Retention`, mặc định của Java là `RetentionPolicy.CLASS`.

**Phân biệt định nghĩa và lần sử dụng:** `SourceTag.class` (class file của chính *annotation type*) có thể vẫn được tạo bởi `javac`, và meta-annotation `@Retention(SOURCE)` trên định nghĩa type cũng có thể xuất hiện trong bytecode của định nghĩa đó. Điều bị loại bỏ theo SOURCE là **lần sử dụng `@SourceTag` trên class/field/method/type-use khác**.

## 2. Processor đọc SOURCE annotation bằng API nào?

JSR 269 (Pluggable Annotation Processing API) sử dụng các giao diện trong `javax.annotation.processing` và `javax.lang.model`.

Các thành phần quan trọng:

- `javax.annotation.processing.Processor` hoặc `AbstractProcessor`: nơi triển khai logic xử lý khi compiler gọi.
- `ProcessingEnvironment`: cung cấp `Elements`, `Types`, `Messager`, `Filer` và tùy chọn xử lý.
- `RoundEnvironment`: cung cấp các root elements của vòng xử lý và các thao tác như `getElementsAnnotatedWith(...)`.
- `Element`: mô hình **khai báo** trong chương trình, ví dụ class, method, field, parameter, package.
- `TypeMirror`: mô hình **kiểu Java** được dùng ở một vị trí, ví dụ kiểu của field, kiểu trả về, generic argument, mảng hoặc wildcard.
- `AnnotationMirror`: dạng mô hình của annotation trong compiler, không đòi hỏi tạo ra annotation object bằng Java reflection.
- `AnnotatedConstruct.getAnnotationMirrors()`: đọc annotation mirrors trên một `Element` **hoặc `TypeMirror`** phù hợp.

Ví dụ processor thường xử lý annotation ở khai báo class:

```java
for (Element element : roundEnv.getElementsAnnotatedWith(CompileCheck.class)) {
    // element đại diện cho declaration mang @CompileCheck.
}
```

Nhưng lời gọi `getElementsAnnotatedWith(...)` trả **các Element được đánh dấu phù hợp**, **không phải danh sách mọi vị trí syntax của annotation trong cây AST**. Đây là giới hạn quan trọng khi annotation nằm sâu ở **type-use** như đối số generic.

Một annotation processor tiêu chuẩn không phải là runtime reflection, và không cần `@Retention(RUNTIME)` để thấy annotation nguồn; tuy nhiên processor phải được compiler **đăng ký/kích hoạt** phù hợp, phải nằm trong môi trường xử lý nguồn có liên quan và phải dùng API có thể biểu diễn vị trí mà annotation thực sự được gắn.

## 3. TYPE_USE khác với annotation trên declaration

Từ Java 8, `ElementType.TYPE_USE` cho phép một annotation được đặt trên vị trí **sử dụng kiểu** (*type use*), ví dụ:

```java
List<@TypeNote("element") String> names;
```

Ở đây `@TypeNote` gắn vào **kiểu `String` bên trong đối số kiểu của `List`**, không trực tiếp gắn vào khai báo field `names` theo nghĩa metadata declaration.

So sánh:

```java
@SourceTag("declaration")
class Catalog {
    List<@TypeNote("argument") String> items;
}
```

- `@SourceTag` đánh dấu **class declaration** `Catalog`, nên `Catalog` là một `TypeElement` được đánh dấu.
- `@TypeNote` đánh dấu **type argument `String`** trong kiểu của field `items`. Phần tử khai báo field là một `VariableElement`, nhưng annotation nằm trên một **TypeMirror con** của kiểu field.
- Khi chỉ đọc `field.getAnnotationMirrors()` hoặc hỏi `RoundEnvironment.getElementsAnnotatedWith(TypeNote.class)`, chương trình **không được phép giả định** sẽ thấy mọi annotation nằm bên trong cấu trúc kiểu generic. Phải đi tới đúng kiểu sử dụng và đọc `getAnnotationMirrors()` trên `TypeMirror` đó.

Phân biệt thêm ba target thường nhầm:

| Target | Vị trí | Ví dụ |
| --- | --- | --- |
| `ElementType.TYPE` | Khai báo class, interface, annotation type... | `@SourceTag class Catalog {}` |
| `ElementType.TYPE_PARAMETER` | Khai báo biến kiểu trong generic | `class Box<@Marker T> {}` |
| `ElementType.TYPE_USE` | Vị trí sử dụng kiểu | `List<@Marker String>`; kiểu cast, kiểu trả về, đối số kiểu... |

Nếu một annotation type chỉ có target `TYPE_USE`, nó không được hiểu là annotation declaration ở mọi vị trí. Mặt khác, một annotation có nhiều target có thể tạo ra các diễn giải phụ thuộc **ngữ cảnh cú pháp chính xác**; khi mục đích là kiểm tra type-use, hãy dùng API type model thay vì mặc định dựa vào Element annotations.

## 4. Chương trình Java 17+ chạy được: SOURCE declaration và SOURCE type-use

Ví dụ này tạo một annotation processor thực sự, rồi dùng processor đó để kiểm tra:

1. Annotation `@SourceTag` (retention `SOURCE`) trên khai báo class được tìm qua `RoundEnvironment.getElementsAnnotatedWith`.
2. Annotation `@TypeNote` (retention `SOURCE`) trên đối số kiểu trong `List<@TypeNote String>` **không** được trả về như một element riêng bởi `getElementsAnnotatedWith(TypeNote.class)` trong fixture này.
3. Processor vẫn tìm được `@TypeNote` bằng cách lấy `TypeMirror` của field, đi đến generic type argument và đọc `getAnnotationMirrors()` trên kiểu thành phần đó.
4. Sau khi biên dịch, class file của `Sample` không còn **các lần sử dụng** `@SourceTag`/`@TypeNote` vì retention là `SOURCE`.

### 4.1. Cấu trúc tệp

```text
src/
├── demo/
│   ├── SourceTag.java
│   ├── TypeNote.java
│   └── Sample.java
└── tools/
    └── InspectProcessor.java
```

Để chạy chỉ cần JDK 17 trở lên. Hai annotation type và processor sẽ được biên dịch trước để processor có thể tải annotation type của nó; sau đó compiler dùng `-processor` kích hoạt processor khi biên dịch mã có annotation.

### Tệp 1: `src/demo/SourceTag.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface SourceTag {
    String value();
}
```

`SourceTag` là annotation dùng trên **khai báo type**. Việc đặt `@Retention(SOURCE)` không ngăn processor quan sát lần sử dụng khi compiler còn xử lý nguồn.

### Tệp 2: `src/demo/TypeNote.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE_USE)
public @interface TypeNote {
    String value();
}
```

`TypeNote` có target **`TYPE_USE`**, và trong chương trình này được dùng trên **generic type argument**, tức một vị trí bên trong một `DeclaredType`.

### Tệp 3: `src/demo/Sample.java`

```java
package demo;

import java.util.List;

@SourceTag("compile-only")
public class Sample {
    private List<@TypeNote("item-type") String> names;

    public List<@TypeNote("result-type") String> names() {
        return names;
    }
}
```

`@SourceTag("compile-only")` gắn vào class `Sample`. Hai lần dùng `@TypeNote` nằm ở **đối số kiểu `String`**, một lần trong kiểu field `names` và một lần trong kiểu trả về của method `names()`. Để minh họa giới hạn API rõ ràng, processor bên dưới chủ động đi vào generic type argument của **field**; annotation trong kiểu trả về là trường hợp có thể mở rộng thêm.

### Tệp 4: `src/tools/InspectProcessor.java`

```java
package tools;

import demo.SourceTag;
import demo.TypeNote;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeMirror;

@SupportedAnnotationTypes({"demo.SourceTag", "demo.TypeNote"})
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class InspectProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) {
            return false;
        }

        System.out.println("DECLARED-MATCHES="
                + round.getElementsAnnotatedWith(SourceTag.class).size());
        System.out.println("TYPE-USE-MATCHES="
                + round.getElementsAnnotatedWith(TypeNote.class).size());

        for (Element cls : round.getElementsAnnotatedWith(SourceTag.class)) {
            SourceTag tag = cls.getAnnotation(SourceTag.class);
            System.out.println("SOURCE-TAG=" + tag.value());

            for (Element member : cls.getEnclosedElements()) {
                if (member.getKind() != ElementKind.FIELD) {
                    continue;
                }

                DeclaredType listType = (DeclaredType) member.asType();
                TypeMirror typeArg = listType.getTypeArguments().get(0);
                for (AnnotationMirror mirror : typeArg.getAnnotationMirrors()) {
                    System.out.println("TYPE-ARG="
                            + mirror.getAnnotationType()
                                    .asElement().getSimpleName());
                }
            }
        }
        return false;
    }
}
```

**Giải thích processor:**

- `@SupportedAnnotationTypes` liệt kê những annotation type mà processor hỗ trợ. `@SupportedSourceVersion(RELEASE_17)` xác định mức ngôn ngữ mà processor công bố hỗ trợ; `javac --release 17` giúp thống nhất thí nghiệm.
- `process(...)` có thể được gọi qua **nhiều round**. Mã kiểm tra `round.processingOver()` để bỏ qua round cuối; ví dụ không sinh source mới nên đầu ra dự kiến được in một lần ở round có annotation phù hợp.
- `round.getElementsAnnotatedWith(SourceTag.class)` tìm `TypeElement` của `Sample` vì annotation nằm trên **declaration**.
- `cls.getAnnotation(SourceTag.class)` là tiện ích **compile-time language-model API** để đọc annotation nguồn trong processor; nó **không phải** `java.lang.Class.getAnnotation(...)` của reflection. Trong nhiều processor, dùng `AnnotationMirror` có lợi khi không muốn tải annotation type từ processor class loader.
- `round.getElementsAnnotatedWith(TypeNote.class)` **không trả một Element riêng cho generic type argument `String`** trong fixture này; đầu ra quan sát được là `0`. Điều này minh họa giới hạn của API tìm **Element**, không phải một khẳng định rằng processor không thể đọc `TYPE_USE`.
- `member.asType()` trả kiểu khai báo của field. Với trường `List<String> names`, kiểu đó là `DeclaredType`; `getTypeArguments().get(0)` lấy `TypeMirror` của `String` nằm trong `List`.
- `typeArg.getAnnotationMirrors()` là chìa khóa: nó cung cấp annotation trên **type use** tương ứng, kể cả retention `SOURCE` khi mô hình nguồn có thông tin đó.

Đoạn xử lý này cố ý giới hạn ở **fixture biết trước có một field với một type argument**. Processor dùng trong sản phẩm thực tế phải kiểm tra `TypeKind`, `instanceof DeclaredType`, số lượng type arguments, sự đa dạng member và trạng thái code không hợp lệ/đang biên dịch dở trước khi ép kiểu hoặc lấy `get(0)`.

### 4.2. Lệnh javac (dùng JDK 17+)

Đứng ở thư mục chứa `src`, tạo sẵn hai thư mục output `classes` và `out` hoặc để `javac -d` tạo cây package dưới thư mục output:

```bash
javac --release 17 -d classes src/demo/SourceTag.java src/demo/TypeNote.java src/tools/InspectProcessor.java
javac --release 17 -cp classes -processorpath classes -processor tools.InspectProcessor -d out src/demo/SourceTag.java src/demo/TypeNote.java src/demo/Sample.java
```

Giai đoạn 1 biên dịch annotation type và processor. Giai đoạn 2 dùng `-processorpath classes` và `-processor tools.InspectProcessor` để **kích hoạt tường minh** processor; không cần phụ thuộc việc IDE hoặc build tool tự phát hiện processor. `-cp classes` giúp compiler nhìn thấy các annotation types đã biên dịch; các tệp annotation nguồn cũng được liệt kê trong lượt biên dịch mẫu.

**Stdout của lệnh `javac` thứ hai:**

```text
DECLARED-MATCHES=1
TYPE-USE-MATCHES=0
SOURCE-TAG=compile-only
TYPE-ARG=TypeNote
```

Đây là kết quả đã được chạy kiểm chứng với `javac 21 --release 17`; các thông số của fixture và API đều tương thích Java 17. Nếu processor khác tạo thêm nguồn hoặc chương trình build dùng nhiều round, số lần in có thể khác; vì vậy **không dùng số round của ví dụ như hợp đồng cho mọi processor**.

Để quan sát class file sau biên dịch:

```bash
javap -v -classpath out demo.Sample
```

Khi xem `demo.Sample`, sẽ **không có lần dùng `@SourceTag("compile-only")` và `@TypeNote("item-type"/"result-type")`** trong metadata annotation tương ứng của `Sample.class`, vì cả hai type đều dùng retention `SOURCE`. Đừng tìm trên `SourceTag.class`/`TypeNote.class` rồi suy luận sai: đây là class files của *định nghĩa* annotation types, không phải `Sample` được đánh dấu.

Chương trình mẫu không có phương thức `main`: **output ở đây xuất hiện khi biên dịch nhờ annotation processor**, chứ không phải kết quả của lệnh `java demo.Sample`.

## 5. Vì sao getElementsAnnotatedWith không thay thế việc đọc TypeMirror?

Mô hình JSR 269 phân biệt **khai báo** và **kiểu sử dụng**:

```text
TypeElement Sample
├── annotation trên declaration: @SourceTag("compile-only")
├── VariableElement names
│   └── DeclaredType List<...>
│       └── TypeMirror String
│           └── @TypeNote("item-type")   ← TYPE_USE
└── ExecutableElement names()
    └── returnType: DeclaredType List<...>
        └── TypeMirror String
            └── @TypeNote("result-type") ← TYPE_USE
```

`RoundEnvironment.getElementsAnnotatedWith(...)` giúp tìm **elements** được đánh dấu. Nó không phải một truy vấn đệ quy mọi `TypeMirror` con, mọi biến kiểu, mọi type argument và mọi biểu thức Java có annotation.

Với `TYPE_USE`, processor phải đi tới **vị trí kiểu phù hợp**:

- Field: `VariableElement.asType()` rồi tìm đúng cấp trong `DeclaredType`/`ArrayType`/`WildcardType`/... .
- Method: `ExecutableElement.getReturnType()`, `getParameters()` và kiểu của tham số, kiểu ngoại lệ hoặc type parameters khi có.
- Supertype: `TypeElement.getSuperclass()` và `getInterfaces()` nếu annotation nằm trên những lần sử dụng kiểu liên quan.
- Generic nested type: lần theo `DeclaredType.getTypeArguments()` nhiều cấp. Một kiểu `Map<@A String, List<@B Integer>>` có annotation ở **hai đường đi** khác nhau.
- Array: annotation có thể nằm trên kiểu thành phần hoặc mức mảng khác nhau; không mặc định mọi annotation đều gắn ở cùng cấp.

`Element.getAnnotationMirrors()` và `TypeMirror.getAnnotationMirrors()` đều hợp lệ, nhưng chúng xem **hai đối tượng mô hình khác nhau**. Lấy annotation mirrors từ field declaration **không đảm bảo tìm được** annotation chỉ gắn với type argument. Tương tự, lấy annotation ở outer type `List<...>` không đương nhiên bao gồm annotation ở type argument `String`.

Không nên chỉ đếm `getElementsAnnotatedWith` rồi kết luận “processor không hỗ trợ annotation trên kiểu sử dụng”. Kết luận đúng là: **annotation trên type-use cần đọc đúng phần của type model hoặc đi sâu vào cây cú pháp khi cần**.

## 6. Những giới hạn thực tế của mô hình annotation processing tiêu chuẩn

### 6.1. SOURCE retention không phải là giới hạn

Một `@Retention(SOURCE)` trên khai báo class có thể được processor đọc ngay trong lượt biên dịch. Một `@Retention(SOURCE)` trên type argument cũng có thể được đọc bằng `TypeMirror.getAnnotationMirrors()` tương ứng như ví dụ. Việc không tìm được annotation thường do **vị trí hoặc API đang truy vấn**, không phải vì retention là `SOURCE`.

Ngược lại, reflection khi chạy `java` **không có phép màu** để khôi phục những lần dùng annotation SOURCE đã bị bỏ khỏi bytecode.

### 6.2. Không phải mọi vị trí type-use đều là Element

Java cho phép annotation type-use ở nhiều vị trí, chẳng hạn generic arguments, array component, cast, `instanceof` pattern phù hợp, biểu thức tạo object, kiểu của biến cục bộ và những vị trí kiểu khác được ngôn ngữ cho phép. Không phải mọi vị trí cú pháp ấy đều được biểu diễn dưới dạng một `Element` có thể thu được qua `RoundEnvironment.getElementsAnnotatedWith`.

`TypeMirror` rất hữu ích khi kiểu được liên hệ với những declaration như field, method, parameter và supertype. Nhưng để kiểm tra **chính xác một annotation trên cast, biểu thức, nhánh cú pháp hoặc vị trí biến cục bộ**, mô hình `javax.lang.model` có thể không đủ thông tin. Với compiler `javac`, có thể cần API cây cú pháp `com.sun.source.tree` và `com.sun.source.util.Trees`/`TreePathScanner` để khảo sát `AnnotatedTypeTree` và những vị trí AST tương ứng.

**Quan trọng:** `com.sun.source.*` là các API compiler tree được `javac` cung cấp; mức hỗ trợ/khả năng liên kết vào compiler có thể khác giữa công cụ hoặc trình biên dịch. Không coi chúng là một phần bắt buộc của mọi implementation JSR 269.

### 6.3. Processor không quét mọi thứ trên classpath

Trong một lượt `javac`, processor hoạt động theo các **root elements và rounds** mà compiler cung cấp, cùng các type mà nó có thể truy vấn thông qua model. Nó **không tự rà toàn bộ tệp nguồn/cả dependency repository** để tìm mọi annotation type-use. Đặc biệt, SOURCE annotation vốn không còn được lưu trên class file của dependency đã biên dịch, nên processor đang xử lý một project khác **không thể đọc lại các lần dùng SOURCE từ class file dependency ấy**.

Nếu bài toán cần phân tích toàn bộ dependency đã biên dịch, phải chuyển sang cách tiếp cận bytecode; tuy nhiên SOURCE annotations trên lần dùng đã biên dịch vẫn không có trong bytecode, bất kể công cụ đọc bytecode mạnh đến đâu.

### 6.4. Rounds, discovery và sự kích hoạt processor

`@SupportedAnnotationTypes` khai báo phạm vi annotation names được hỗ trợ, nhưng không đồng nghĩa “cứ annotation xuất hiện ở **bất kỳ type-use nào** thì processor luôn tự được discover và xử lý”. Khả năng kích hoạt còn phụ thuộc cấu hình build, processor path, processor được chọn, round hiện tại và những loại phần tử mà compiler đưa vào xử lý.

Trong ví dụ, processor được **kích hoạt tường minh bằng `-processor tools.InspectProcessor`** và có một `@SourceTag` trên class; ta không dựa vào việc một annotation chỉ nằm trong nested generic argument có đủ để kích hoạt processor ở mọi môi trường hay không.

Từ các phiên bản JDK/build tool khác nhau, chính sách tự phát hiện annotation processors có thể khác. Với một bài kiểm thử hoặc pipeline cần hành vi có thể tái lập, hãy cấu hình processor rõ ràng.

### 6.5. Annotation processor không phải nơi chạy logic ở runtime

Một processor thường có thể dùng `Messager` để phát cảnh báo/lỗi compile-time, `Filer` để sinh source/resource, hoặc phân tích kiểu và element theo quy tắc. Nó **không làm cho annotation type được giữ ở runtime**, trừ khi annotation type vốn có retention phù hợp.

Một annotation `SOURCE` phù hợp cho lint/kiểm tra compile-time, sinh adapter, tạo mã boilerplate theo quy tắc, hoặc kiểm tra cấu trúc kiểu khi nguồn đang được biên dịch. Nếu framework cần đọc metadata bằng reflection sau khi deploy, chọn `RUNTIME` cho annotation cần đọc — hoặc tạo ra output trung gian khác ở compile time.

## 7. AnnotationMirrors, giá trị phần tử và an toàn khi phân tích

`getAnnotationMirrors()` trả các đối tượng `AnnotationMirror`, mỗi mirror cho biết **annotation type** và các giá trị element được chỉ định trong nguồn/bytecode model. Ví dụ:

```java
for (AnnotationMirror annotation : typeArg.getAnnotationMirrors()) {
    System.out.println(annotation.getAnnotationType());
}
```

Đoạn trên là minh họa giả sử đã có `TypeMirror typeArg`; chương trình đầy đủ ở mục 4 dùng đúng API này.

Nếu muốn đọc giá trị `"item-type"` của `@TypeNote("item-type")`, có hai cách thường dùng:

1. Dùng typed proxy qua `typeMirror.getAnnotation(TypeNote.class)` trong ngữ cảnh processor có thể tải type annotation tương ứng, rồi gọi `value()`.
2. Dùng `AnnotationMirror` và `ElementValuesWithDefaults` qua `Elements.getElementValuesWithDefaults(annotation)` để có mô hình giá trị gồm cả các default phù hợp. Đây là cách tổng quát hơn khi xử lý nhiều annotation types, enum types hoặc những class literals khó tải vào processor class loader.

Khi đọc model:

- Không giả định annotation mirror luôn nằm ở `index 0` vì có thể có nhiều annotation.
- Kiểm tra đúng annotation type bằng tên/các phần tử mô hình thay vì ép kiểu bừa.
- Không giả định mọi `TypeMirror` đều là `DeclaredType`; primitive, array, wildcard, type variable, intersection, error type có biểu diễn khác.
- Nếu cần đường đi chính xác trong generic nested types, viết hàm duyệt **từng tầng cấu trúc kiểu**, không lấy duy nhất `getTypeArguments().get(0)` cho mọi trường hợp.
- Khi xử lý chương trình đang có lỗi compile, có thể gặp `ErrorType`/model chưa hoàn chỉnh và cần báo chẩn đoán an toàn thay vì crash processor.

## 8. So sánh với reflection và bytecode analysis

| Câu hỏi | JSR 269 processor khi biên dịch | Class-file analyzer | Java reflection khi chạy |
| --- | --- | --- | --- |
| Nhìn `@Retention(SOURCE)` trên class đang biên dịch? | Có thể | Không, sau khi `SOURCE` bị bỏ khỏi class file đích | Không |
| Nhìn SOURCE trên `List<@TypeNote String>` trong nguồn đang biên dịch? | Có thể nếu đi đúng type model/AST | Không | Không |
| Nhìn CLASS annotation còn lưu trong class file? | Có thể với model compiler ở ngữ cảnh phù hợp | Có | Không qua `getAnnotation` thông thường |
| Nhìn RUNTIME annotation? | Có thể | Có | Có khi đúng phần tử và API |
| Phát hiện annotation ở một cast/local type-use? | Có thể cần tree API của compiler | Nếu retention còn lưu và vị trí được mã hóa phù hợp | Không được bảo đảm bằng các API declaration reflection thông thường |
| Tạo cảnh báo tại vị trí source? | Có, dùng `Messager`/compiler tree khi thích hợp | Không trực tiếp có mô hình source compile-time tiêu chuẩn | Không |
| Tạo object Java từ annotation? | Không phải mục đích chính | Không phải mục đích chính | Không tự tạo đối tượng nghiệp vụ, chỉ trả metadata reflection |

Reflection cũng có API cho type-use còn giữ đến runtime, ví dụ `AnnotatedType` và `AnnotatedParameterizedType`. Chúng là **API runtime riêng**, không phải `javax.lang.model.type.TypeMirror`. SOURCE annotation không hiện trong những API runtime này vì retention đã loại bỏ lần dùng annotation khỏi class file.

## 9. Các lỗi hiểu sai thường gặp

### Lỗi 1: “Retention SOURCE nghĩa là processor không thấy annotation”

Sai. `@Retention(SOURCE)` có thể được compiler/processor quan sát khi đang xử lý nguồn. Annotation biến mất khỏi **class file đích sau biên dịch**, không biến mất ngay khi compiler bắt đầu đọc nguồn.

### Lỗi 2: “getElementsAnnotatedWith sẽ tìm mọi @TypeNote”

Không đủ. API trả **Element**; annotation trên nested type argument, cast và các vị trí type-use khác có thể không tương ứng một declaration element được API này báo về. Xác định chính xác vị trí cú pháp và đọc `TypeMirror.getAnnotationMirrors()` hoặc tree API phù hợp.

### Lỗi 3: “getAnnotationMirrors trên field phải thấy annotation trong List<@TypeNote String>”

Không nhất thiết. Field declaration và `String` type argument là **hai thực thể model khác nhau**. Trong ví dụ này phải đi từ `VariableElement.asType()` → `DeclaredType.getTypeArguments()` → `TypeMirror.getAnnotationMirrors()`.

### Lỗi 4: “Đã có processor thì SOURCE sẽ có trong runtime bytecode”

Sai. Processor có thể **sinh thêm mã nguồn/tài nguyên** chứa kết quả phân tích nhưng không tự thay đổi retention của lần dùng SOURCE gốc. `Sample.class` trong ví dụ không chứa những lần dùng SOURCE annotations ấy.

### Lỗi 5: “Cứ viết @Target(TYPE_USE) là processor tự kiểm tra mọi biểu thức”

Sai. `@Target` làm hợp lệ vị trí gắn annotation; nó không tự viết logic phân tích AST. Muốn xác thực type-use ở mọi vị trí, phải xác định mức bao phủ và chọn model/tree APIs phù hợp.

### Lỗi 6: “Có thể đọc annotation SOURCE từ dependency JAR đã compile”

Không thể đọc lại một lần dùng SOURCE đã bị loại khỏi bytecode của dependency. Muốn kiểm tra các lần dùng ấy phải xử lý khi biên dịch nguồn dependency, hoặc dùng một kết quả phân tích được xuất ra riêng.

### Lỗi 7: “Processor phải luôn được gọi chỉ vì annotation có mặt trên type argument”

Không nên dựa vào điều đó mà không kiểm thử cấu hình processor. Trong ví dụ, ta kích hoạt processor **tường minh** và có annotation trên declaration để kiểm chứng dễ dàng. Build/CI cần cấu hình rõ processor path, lựa chọn processor và round behavior.

## 10. Quy trình thiết kế SOURCE annotation cho kiểm tra type-use

Một quy trình áp dụng trong dự án:

1. **Xác định chính sách retention:** nếu chỉ cần kiểm tra ở compile time, `SOURCE` thường phù hợp; không chọn `RUNTIME` chỉ để processor đọc được.
2. **Xác định đích:** declaration dùng `TYPE`/`FIELD`/`METHOD`/...; type-use dùng `TYPE_USE`; type-parameter declaration dùng `TYPE_PARAMETER`. Có thể phối hợp target khi thực sự cần.
3. **Viết processor có thể tái lập:** khai báo supported annotation types, source version, cấu hình processor path và chọn processor tường minh trong bài test.
4. **Bắt đầu từ root/declaration elements:** dùng `RoundEnvironment` cho annotation declarations; lấy các `Element` cần phân tích.
5. **Duyệt type model:** tại field/method/parameter/supertype, lấy `TypeMirror`, lần theo generic arguments, array component, wildcard bound, v.v. và đọc annotation mirrors ở đúng cấp.
6. **Đánh giá giới hạn của model:** nếu cần local variable, cast hoặc cú pháp expression, cân nhắc sử dụng `Trees`/`TreePathScanner` trong môi trường compiler hỗ trợ; không tuyên bố quét toàn bộ chỉ dựa trên `getElementsAnnotatedWith`.
7. **Phát chẩn đoán rõ ràng:** dùng `Messager` và gắn đúng vị trí khi có thể; xử lý trường hợp type đang có lỗi hoặc compiler chạy nhiều rounds.
8. **Kiểm chứng class file:** với SOURCE, `javap -v` trên class **được đánh dấu** không cho thấy lần sử dụng SOURCE annotation. Nếu thấy tên annotation trong class file của chính annotation type, đó là tình huống khác.
9. **Kiểm thử phản ví dụ:** một annotation trên class declaration, một annotation trên nested type argument, một annotation trong kiểu trả về, một annotation ở vị trí expression/cast nếu dự án cần. Đảm bảo code phân tích thật sự kiểm tra được từng vị trí đã cam kết.

**Ghi nhớ:** SOURCE annotation **có thể được annotation processor xử lý khi biên dịch**, kể cả trong nhiều tình huống `TYPE_USE`. Giới hạn không nằm ở chữ `SOURCE`, mà nằm ở **khả năng nhìn thấy vị trí annotation bằng đúng compile-time API**. `RoundEnvironment.getElementsAnnotatedWith(...)` hướng tới declaration elements, trong khi annotation trên nested type-use thường phải đi qua `TypeMirror.getAnnotationMirrors()` hoặc compiler tree API. Sau biên dịch, lần dùng SOURCE annotation không còn trong class file đích để reflection/runtime hoặc bytecode tools đọc lại.
