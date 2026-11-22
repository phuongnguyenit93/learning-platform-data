# Kiểm thử công cụ phân tích và annotation processor cho type annotation trong Java

## 1. Mục tiêu và phạm vi

Java 8 giới thiệu **type-use annotations**: annotation có thể nằm trên một lần dùng kiểu, chẳng hạn `List<@Checked String>`, `String @Checked []` hoặc `(@Checked String) value`. Cú pháp này **vẫn hiện hành** trên các JDK được duy trì. Tuy nhiên, bản thân annotation không làm Java tự hiểu một quy tắc nghiệp vụ. Muốn một annotation có hiệu lực kiểm tra, cần **công cụ phân tích** và **bộ kiểm thử chính công cụ đó**.

Mục tiêu của bài là kiểm thử độ tin cậy của hai nhóm công cụ:

- **Annotation processor** dùng API `javax.annotation.processing` và `javax.lang.model` (JSR 269) để kiểm tra khai báo, kiểu, annotation metadata, hoặc sinh mã trong các vòng xử lý của compiler.
- **Static analysis/type checker** theo dõi ràng buộc trên lần dùng kiểu và, khi cần, phân tích expression/control flow, ví dụ cast, gán giá trị hoặc đường đi có thể null. Công cụ có thể được triển khai bằng API compiler, plugin hoặc framework phân tích phù hợp.

Bạn sẽ học cách dựng **test dương** (đầu vào hợp lệ → compile thành công), **test âm** (đầu vào sai → compiler báo đúng lỗi), và **test tích hợp** (processor thực sự chạy trong build, không bị vô tình bỏ qua). Đồng thời phân biệt **annotation ở declaration, nested generic argument, array dimension và cast**; cách dùng `TypeMirror` và khi nào cần AST thay vì chỉ duyệt `Element`.

Bài chỉ dùng những kiến thức còn áp dụng: `@Target(TYPE_USE)`, `AbstractProcessor`, `RoundEnvironment`, `Messager`, `TypeMirror`, `DeclaredType`, `ArrayType`, compiler diagnostics, và cấu hình processing **tường minh trên JDK hiện đại**. Mã thực hành có thể biên dịch với một JDK 17+ đang được cập nhật; API ví dụ sử dụng đặc tính Java 8 để dễ đối chiếu.

## 2. Vì sao kiểm thử processor cũng quan trọng như kiểm thử ứng dụng?

Giả sử một nhóm định nghĩa `@Verified` để đánh dấu kiểu phải được công cụ kiểm tra. Mã:

~~~java
java.util.List<@Verified String> names;
~~~

chỉ có ý nghĩa cưỡng chế nếu compiler/plugin/processor biết **`@Verified` nghĩa là gì**, tìm thấy đúng annotation trong cây kiểu và phát diagnostic khi quy tắc bị vi phạm. Có nhiều tình huống nguy hiểm mà một build vẫn **xanh**:

- Processor không được bật trong compiler invocation.
- `@Target` cho phép vị trí dùng, nhưng processor chỉ quét annotation trên khai báo class/field mà bỏ qua generic type argument.
- Processor nhìn thấy `String[]` mà không phân biệt annotation trên **array reference** hay **element type**.
- Công cụ chỉ xem `Element`, trong khi annotation nằm trên **cast expression** bên trong method body.
- Processor được compile đúng nhưng không được đăng ký với `-processor` hoặc service loader; build không thực thi kiểm tra.
- Compiler/plugin nâng phiên bản, diagnostic mất hoặc biến thành warning không làm CI fail.
- Build incremental dùng kết quả cũ, che lỗi hiện tại; clean build lại không khớp.

**Kết luận:** “Mã có annotation” và “mã được kiểm đúng” là hai mệnh đề khác nhau. Bộ test phải chứng minh **công cụ chạy thật**, phân tích **đúng vị trí**, và trả về **kết quả kiểm chứng được**.

## 3. Phân biệt bốn tầng kiểm tra

| Tầng | Câu hỏi | Ví dụ bằng chứng |
| --- | --- | --- |
| **Cú pháp Java** | Annotation có target hợp lệ tại vị trí dùng kiểu? | `javac` cho phép `List<@Mark String>` khi `@Mark` có `TYPE_USE` |
| **Metadata/processor** | Công cụ tìm được annotation **đúng tầng kiểu**? | `TypeMirror.getAnnotationMirrors()` ở type argument/array type |
| **Phân tích ngữ nghĩa** | Công cụ có thật sự kiểm luật riêng của project? | Test âm khiến compiler báo `Diagnostic.Kind.ERROR` |
| **Tích hợp build** | CI bật processor/checker với đúng classpath/version? | Test dương và âm chạy trong build thật, kết quả không phụ thuộc cache |

Một annotation bất kỳ tên `@NonNull` **không** khiến Java SE tự chặn `null` hoặc tự chặn cast không hợp lệ. Annotation processor đơn giản cũng **không tự động trở thành flow-sensitive nullness checker**. Nếu muốn bảo đảm nullness qua các nhánh `if`, method calls, generics, casts và override, cần một phân tích ngữ nghĩa có mô hình dữ liệu và quy tắc rõ ràng, thường mạnh hơn việc duyệt `Element`.

### Chọn retention phù hợp

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.CLASS)
public @interface Mark {
}
~~~

- `TYPE_USE` cho phép annotation trên generic argument, array dimension, cast, type bound và các type uses khác.
- `CLASS` giữ metadata tương ứng trong class file nhưng **core reflection không bảo đảm truy xuất nó như runtime-visible annotation**. Đây là lựa chọn hữu ích nếu processor/bytecode tool cần metadata mà ứng dụng không cần phản chiếu annotation lúc chạy.
- `RUNTIME` chỉ dùng khi một thành phần runtime thực sự đọc annotation qua reflection hoặc metadata.
- `SOURCE` phù hợp khi thông tin chỉ dùng khi xử lý mã nguồn.
- `@Target(FIELD)` đơn thuần **không thay thế** `TYPE_USE` cho `List<@Mark String>` hay `(@Mark String) input`.

Không mặc định tất cả annotation đều phải dùng `RUNTIME`. Lựa chọn đúng dựa trên **người tiêu thụ annotation** và kiểm thử thực tế ở từng tầng.

## 4. Type-use annotation nằm ở đâu trong compiler model?

Ví dụ:

~~~java
import java.util.List;
import java.util.Map;

class Inputs {
    List<@Mark String> names;
    Map<String, List<@Mark Integer>> counts;
    String @Mark [] references;
    @Mark String[] elements;

    String cast(Object input) {
        return (@Mark String) input;
    }
}
~~~

Đây là trích đoạn minh họa, cần `@Mark` từ mục trước.

- `names`: annotation ở **type argument `String`**, không phải annotation declaration trên field `names`.
- `counts`: annotation ở **type argument lồng sâu `Integer`**, phải đi qua hai mức `DeclaredType`.
- `references`: annotation trên **mảng ngoài `String[]`**.
- `elements`: annotation trước `String` nhắm vào **kiểu phần tử**, không phải mảng ngoài.
- `cast`: annotation ở **kiểu đích của expression cast** trong method body, không phải field hoặc signature của method.

Vì vậy, một processor chỉ dùng:

~~~java
roundEnv.getElementsAnnotatedWith(Mark.class);
~~~

**không phải** lời giải đầy đủ để tìm mọi `@Mark` ở type-use. API này trả về các **elements có annotation tương ứng theo hợp đồng xử lý**, không duyệt tự động mọi node trong cây generic, mảng và expression.

Đối với annotation trên kiểu, điểm bắt đầu hữu ích là:

~~~java
// Trong processor, với VariableElement field:
javax.lang.model.type.TypeMirror type = field.asType();
java.util.List<? extends javax.lang.model.element.AnnotationMirror> mirrors =
    type.getAnnotationMirrors();
~~~

Nhưng `type.getAnnotationMirrors()` trả annotation **trực tiếp trên chính TypeMirror đang xét**. Với `List<@Mark String>`, root `List` thường không có `@Mark`: cần lấy `DeclaredType.getTypeArguments().get(0)` trước. Với `String @Mark []`, annotation ở `ArrayType`; với `@Mark String[]`, cần đi vào `ArrayType.getComponentType()`.

## 5. Test tối thiểu có thể chạy: annotation + processor + hai fixture

Bài thực hành xây một processor nhỏ để **xác nhận vị trí** annotation trên generic argument và array type. Test này **không khẳng định** chứng minh null-safety; nó cố tình chỉ thực thi hợp đồng có thể quan sát được: một số field phải được đánh dấu `@Mark` ở đúng tầng.

Tạo **bốn file** chung một thư mục, đúng tên:

~~~text
Mark.java
TypeUseProcessor.java
GoodSample.java
BadSample.java
~~~

Chạy trên JDK hiện đại có `javac`; tạo hai thư mục output `processor-out` và `classes` trước khi biên dịch. Các ví dụ không yêu cầu Maven, Gradle hay dependency bên ngoài.

### 5.1. File Mark.java

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.CLASS)
public @interface Mark {
}
~~~

Annotation này có runtime/classfile policy xác định, và Java compiler chấp nhận nó trong generic argument, array và cast.

### 5.2. File TypeUseProcessor.java

~~~java
import java.util.List;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("*")
public final class TypeUseProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        // Không giới hạn công cụ vào RELEASE_8 nếu dùng compiler mới.
        return SourceVersion.latestSupported();
    }

    private boolean hasMark(TypeMirror type) {
        for (AnnotationMirror annotation : type.getAnnotationMirrors()) {
            if (annotation.getAnnotationType().toString().equals("Mark")) {
                return true;
            }
        }
        return false;
    }

    private void report(Element field, String message) {
        processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR, message, field);
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return false;
        }

        for (Element root : roundEnv.getRootElements()) {
            // Fixture cố ý chỉ dùng các class kết thúc bằng "Sample".
            if (!root.getSimpleName().toString().endsWith("Sample")) {
                continue;
            }

            boolean sawValues = false;
            boolean sawNames = false;

            for (Element member : root.getEnclosedElements()) {
                if (member.getKind() != ElementKind.FIELD) {
                    continue;
                }

                if (member.getSimpleName().contentEquals("values")) {
                    sawValues = true;
                    TypeMirror listType = member.asType();
                    boolean marked = false;

                    if (listType.getKind() == TypeKind.DECLARED) {
                        List<? extends TypeMirror> args =
                            ((DeclaredType) listType).getTypeArguments();
                        marked = args.size() == 1 && hasMark(args.get(0));
                    }

                    if (!marked) {
                        report(member,
                            "values: missing @Mark on generic argument");
                    }
                }

                if (member.getSimpleName().contentEquals("names")) {
                    sawNames = true;
                    // ArrayType root = chính kiểu mảng ngoài.
                    if (!hasMark(member.asType())) {
                        report(member,
                            "names: missing @Mark on outer array type");
                    }
                }
            }

            if (!sawValues || !sawNames) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Sample must declare fields values and names",
                    root);
            }
        }

        // Không claim mọi annotation của toàn bộ compilation.
        return false;
    }
}
~~~

**Cơ chế:**

- `@SupportedAnnotationTypes("*")` là lựa chọn minh họa cho processor **kiểm tra các root elements** kể cả khi annotation chỉ nằm trên các type uses. Nó không đồng nghĩa mọi annotation đã được xét đúng; phải tự duyệt cấu trúc.
- `RoundEnvironment.getRootElements()` cung cấp các root trong vòng processing. Mã chỉ kiểm class tên kết thúc `Sample` để bài thực hành có kết quả rõ ràng; **không nên dùng quy tắc tên này làm thiết kế production**.
- Với `values`, processor yêu cầu `List` có **đúng một** type argument và annotation `@Mark` trực tiếp trên argument. Ví dụ `List<@Mark String>` đạt; `@Mark List<String>` **không** đạt vì nhãn ở root list chứ không ở argument.
- Với `names`, processor yêu cầu annotation trực tiếp trên **root array type**. `String @Mark []` đạt; `@Mark String[]` không đạt vì nhãn nằm ở element type.
- `Messager.printMessage(ERROR, ..., field)` làm compile thất bại và có vị trí nguồn tương ứng; số dòng và cách hiển thị diagnostic do compiler quyết định.
- `getSupportedSourceVersion()` dùng `SourceVersion.latestSupported()` để tránh warning rằng processor hỗ trợ source version quá cũ khi chạy trên JDK mới.
- `return false` phù hợp cho checker hỗ trợ `"*"` vì không giành quyền claim toàn bộ annotation, cho phép processor khác tiếp tục xử lý theo hợp đồng.

Processor này không làm dataflow analysis và **không kiểm cast expression**. Đó là ranh giới có chủ đích được kiểm thử riêng ở mục 8.

### 5.3. GoodSample.java — test dương

~~~java
import java.util.List;

public final class GoodSample {
    List<@Mark String> values;
    String @Mark [] names;

    String cast(Object input) {
        return (@Mark String) input;
    }
}
~~~

`GoodSample` hợp lệ đối với hợp đồng của `TypeUseProcessor`: `values` có tag trên generic argument; `names` có tag trên outer array. Cast được javac kiểm về cú pháp/kiểu Java, nhưng processor này **không cố diễn giải** nó.

### 5.4. BadSample.java — test âm

~~~java
import java.util.List;

public final class BadSample {
    List<String> values;
    String[] names;
}
~~~

Mã Java về mặt ngôn ngữ vẫn hợp lệ, nhưng vi phạm **quy tắc riêng mà processor đặt ra**. Khi processor được bật, compile phải **trả exit code khác 0** và có diagnostics tương ứng `values`, `names`. Đây là bằng chứng khác với test cú pháp `@Target` không hợp lệ.

## 6. Lệnh chạy, kiểm tra kết quả và kiểm tra processor có thực sự được bật

Trong thư mục chứa bốn file, tạo thư mục output bằng lệnh phù hợp với shell đang sử dụng (mỗi lệnh dưới đây dùng tên đường dẫn tương đối; trên Windows dấu phân tách là `\\`, nhưng các đường dẫn không chứa classpath delimiter `:` nên có thể giữ dạng đơn giản).

~~~text
mkdir processor-out
mkdir classes

javac -encoding UTF-8 -d processor-out Mark.java TypeUseProcessor.java

javac -encoding UTF-8 -cp processor-out -processorpath processor-out -processor TypeUseProcessor -d classes GoodSample.java
~~~

**Kỳ vọng:** Lệnh cuối **thành công (exit code 0)**. Nếu compiler không in gì, đó vẫn là kết quả hợp lệ; processor của ví dụ không cố phát thông điệp NOTE khi pass.

Sau đó chạy test âm **riêng biệt**:

~~~text
javac -encoding UTF-8 -cp processor-out -processorpath processor-out -processor TypeUseProcessor -d classes BadSample.java
~~~

**Kỳ vọng:** Exit code **khác 0**, có hai diagnostic ERROR do `TypeUseProcessor` đưa ra:

~~~text
values: missing @Mark on generic argument
names: missing @Mark on outer array type
~~~

Hai dòng trên là **phần nội dung thông điệp** cần tìm, **không phải stdout/stderr đầy đủ**. `javac` còn có thể thêm tên file, số dòng, con trỏ vị trí, tổng số lỗi, hoặc thông tin được định dạng khác nhau theo môi trường. Đừng viết test phụ thuộc số cột/câu chữ trang trí của compiler.

**Bước đối chứng bắt buộc:** chạy cùng `BadSample.java` nhưng tắt processing:

~~~text
javac -proc:none -encoding UTF-8 -cp processor-out -d classes BadSample.java
~~~

Lần này Java compiler thông thường có thể **biên dịch thành công**, vì `List<String>` và `String[]` đều là kiểu Java hợp lệ. Đó chính là minh chứng rằng việc phát hiện vi phạm đến từ **processor**, không tự có trong ngôn ngữ Java.

### JDK 23+ thay đổi mặc định annotation processing

Từ **JDK 23**, `javac` không còn tự bật annotation processing chỉ vì một processor xuất hiện tình cờ trong classpath. Cần cấu hình tường minh như `-processor`, `-processorpath`/`--processor-path`, `--processor-module-path`, `-proc:only` hoặc `-proc:full` theo nhu cầu. Bộ lệnh trên cố ý dùng **`-processor TypeUseProcessor`**, tránh phụ thuộc implicit discovery; đây là cách kiểm thử còn phù hợp trên các JDK mới.

**Đừng hiểu nhầm:** `-proc:only` chạy processing nhưng không sinh class như một lần compile đầy đủ; `-proc:full` chạy processing và compilation. Với test cần class đầu ra, dùng cấu hình chạy đầy đủ; với test chỉ kỳ vọng diagnostic, `-proc:only` có thể phù hợp. `-proc:none` là công cụ đối chứng rõ ràng để chứng minh test âm thực sự phụ thuộc processor.

Khi dùng Maven/Gradle, hãy cấu hình annotation processor **explicitly** qua cơ chế của phiên bản build tool đang được hỗ trợ. Phải kiểm output thực tế của compile task; đừng chỉ thấy dependency processor trên classpath là khẳng định nó đã chạy.

## 7. Mở rộng test cho nested generic và array nhiều chiều

### Nested generic argument

Với:

~~~java
java.util.Map<String, java.util.List<@Mark Integer>> table;
~~~

`Map` là root `DeclaredType`. Để đọc `@Mark` trên `Integer`:

1. Lấy type arguments của `Map` qua `((DeclaredType) type).getTypeArguments()`.
2. Chọn argument thứ hai (kiểu `List<@Mark Integer>`).
3. Cast argument đó sang `DeclaredType` nếu `getKind()==DECLARED`.
4. Chọn argument thứ nhất của `List` (kiểu `@Mark Integer`).
5. Gọi `TypeMirror.getAnnotationMirrors()` **tại node `Integer`**.

Không gọi `getAnnotationMirrors()` ở root `Map` rồi kết luận không có type annotations. Một checker tổng quát nên duyệt cây bằng `TypeVisitor` hoặc nhánh `TypeKind` rõ ràng để không bỏ sót array, wildcard bounds, type variable và nested types.

### Array nhiều chiều

Với:

~~~java
@Mark String @Mark [] @Mark [] matrix;
~~~

Ta có ba vị trí type-use: **outer array**, **component array**, **String element**. Công cụ phải đi qua:

~~~text
ArrayType String[][]  → hasMark(root array)
  ArrayType String[]  → hasMark(component array)
    DeclaredType String → hasMark(element type)
~~~

Trong processor Java, dùng `ArrayType.getComponentType()` để đi từ outer array sang component array rồi đến element type. **`String @Mark []` khác `@Mark String[]`**, dù cả hai có thể compile. Một unit test nên chủ động đổi tag giữa các vị trí và xác nhận kết quả analyzer đổi tương ứng.

Để bao quát type variables và wildcard bounds, thêm fixtures như `List<? extends @Mark Number>`, rồi dùng `WildcardType.getExtendsBound()`. Với generic type parameter declaration, annotation `TYPE_PARAMETER` khác với annotation trên actual type argument; không so sánh chúng bằng một phương thức “find annotations” duy nhất.

### Test nên so sánh cấu trúc, không so sánh chuỗi tùy tiện

Tránh phân tích `TypeMirror.toString()` bằng regex để quyết định annotation đang ở cấp nào; chuỗi đó phục vụ hiển thị, không phải cấu trúc ổn định cho mọi compiler. Thay vào đó, kiểm `TypeKind`, `DeclaredType`, `ArrayType`, `WildcardType` và `AnnotationMirror` của **đúng node**.

## 8. Cast expression cần AST/bytecode analysis, không chỉ Element/TypeMirror của field

Đây là chỗ nhiều processor bỏ sót khi thử `TYPE_USE`. Với:

~~~java
Object input = "OK";
String result = (@Mark String) input;
~~~

Annotation nằm ở **kiểu đích của cast expression**, bên trong thân method. `RoundEnvironment.getElementsAnnotatedWith(Mark.class)` không phải API duyệt tất cả cast expressions. `VariableElement.asType()` của một field cũng không chứa toàn bộ AST của method có cast.

Khi cần xác minh annotation trên cast trong source với `javac`, công cụ có thể sử dụng **JDK Compiler Tree API**: `com.sun.source.util.Trees`, `TreePathScanner`, `com.sun.source.tree.TypeCastTree` và `AnnotatedTypeTree`. Đoạn sau là **minh họa tích hợp trong một processor/plugin chạy với javac**, không phải file độc lập:

~~~java
// Có: Trees trees = Trees.instance(processingEnv);
// Có: TreePath path = trees.getPath(rootElement);
// Và các import com.sun.source.tree.*, com.sun.source.util.*;

new TreePathScanner<Void, Void>() {
    @Override
    public Void visitTypeCast(TypeCastTree node, Void unused) {
        Tree castType = node.getType();
        if (castType instanceof AnnotatedTypeTree) {
            AnnotatedTypeTree annotated = (AnnotatedTypeTree) castType;
            if (!annotated.getAnnotations().isEmpty()) {
                // Kiểm tra tên/loại annotation và quy tắc của project.
            }
        }
        return super.visitTypeCast(node, unused);
    }
}.scan(path, null);
~~~

Giải thích:

- `TypeCastTree` biểu diễn cú pháp phép cast; `AnnotatedTypeTree` biểu diễn type có annotation trong AST.
- Đây là API **gắn với compiler có hỗ trợ Tree API**, không phải API `javax.lang.model` dùng được ở mọi implementation annotation processor. Kiểm tương thích toolchain cụ thể.
- Chỉ đếm có annotation là chưa đủ: nếu có nhiều annotation type, phải xác minh **đúng loại** và semantics; có thể dùng `Trees` và `TreePath`/element/type resolution để liên kết AST với model.
- Nếu công cụ kiểm sau compilation, có thể đọc metadata type annotation trong classfile, bao gồm target dạng cast khi retention và compiler output phù hợp. `javap -v` hữu ích để kiểm tra `RuntimeInvisibleTypeAnnotations` hoặc `RuntimeVisibleTypeAnnotations`, nhưng không thay thế checker chuyên dụng.
- Core reflection như `Field.getAnnotatedType()` đọc metadata của khai báo field/kiểu field; **không có API chung để liệt kê mọi cast expression** trong method body bằng cách gọi reflection lên `Field`.

**Test cast tối thiểu:** một fixture có `(@Mark String) source`, một fixture không có annotation, và một fixture cast thật sự sai kiểu gây `ClassCastException` ở runtime. Compiler/checker nên phân biệt vị trí annotation; JVM cast vẫn hoạt động theo type rules thông thường, annotation không khiến cast an toàn hơn.

## 9. Test processor tạo mã, nhiều processing rounds và generated sources

Một annotation processor có thể **sinh file nguồn** bằng `Filer`. Khi đó javac có thể mở **round xử lý mới** cho các source vừa sinh. Một bài test đúng không chỉ hỏi “có file output chưa?” mà còn kiểm:

1. Processor nhận đúng annotated elements trong round đầu.
2. Generated source có **tên package/class hợp lệ**, compile được và không tạo duplicate types.
3. Không viết cùng file bằng `Filer.createSourceFile` lặp lại trong nhiều rounds, dễ gây `FilerException`.
4. `roundEnv.processingOver()` được tôn trọng; processor không tiếp tục tạo source ở round cuối.
5. Một file generated không chứa marker không hợp lệ, placeholder hoặc code phụ thuộc vào thứ tự duyệt elements không bảo đảm.
6. Cấu hình output `-s` (generated sources) và `-d` (classes) được kiểm tra ở build tool; không lẫn generated output cũ khi clean build.
7. Với incremental builds, một thay đổi input phải khiến generated output liên quan được cập nhật đúng; không để file cũ ẩn lỗi.
8. Error diagnostics được attach vào đúng `Element` hoặc annotation value khi có thể để người dùng tìm vị trí lỗi.

Một thiết kế test tốt có fixture sinh đúng một class định danh, sau đó clean build và xác nhận class đó compile. Một fixture khác gây trùng tên hoặc input thiếu bắt buộc phải **fail có chủ đích** với diagnostic dễ hiểu. Các test này thuộc **processor behavior**, khác với kiểm thử application code dùng class generated.

**Không phụ thuộc processor order** nếu nhiều processors cùng tham gia: nếu có dependency giữa các processors, mô tả cơ chế và kiểm thử compiler rounds thay vì giả định service discovery trả đúng thứ tự như filesystem.

## 10. Kiểm thử tự động bằng JavaCompiler API hoặc JUnit

Trong dự án thật, không cần chỉ dựa vào đọc log. Có thể tạo test harness bằng `javax.tools.JavaCompiler` và `DiagnosticCollector<JavaFileObject>`:

~~~java
// Ý tưởng trong một test method, không phải chương trình độc lập:
javax.tools.JavaCompiler compiler =
    javax.tools.ToolProvider.getSystemJavaCompiler();

javax.tools.DiagnosticCollector<javax.tools.JavaFileObject> diagnostics =
    new javax.tools.DiagnosticCollector<javax.tools.JavaFileObject>();

// Dùng compiler.getTask(...) với các source fixtures,
// options có -processor TypeUseProcessor và -processorpath,
// sau đó task.call() để lấy boolean compile result.
~~~

Dùng JDK thay vì môi trường chỉ có runtime thiếu compiler tooling khi test. Với harness, phải cấu hình file manager, classpath, processor path và output directory đúng. Test nên kiểm:

- **GoodSample:** compilation success, không có `Diagnostic.Kind.ERROR` thuộc quy tắc của processor.
- **BadSample:** compilation failure, chứa diagnostics về `values` và `names`; đừng match nguyên văn path/số dòng nếu không cần.
- **Disabled processor:** `-proc:none` tạo kết quả khác như dự kiến; đây là **canary** chống việc processor bị tắt trong CI.
- **Version matrix:** compiler/toolchain được hỗ trợ vẫn nhận type annotations đúng.
- **Determinism:** cùng input, cấu hình và dependency cho cùng tập diagnostics và generated outputs (bỏ những metadata không ổn định nếu có).

JUnit có thể tổ chức test thành các ca rõ tên, nhưng framework test không tự bật processor hay chặn cache. Phần quan trọng là harness **thực sự gọi compiler** và kiểm exit status/diagnostics/generated files.

## 11. Tổ chức CI: một “canary” không được bỏ qua

Gợi ý phân tách pipeline:

~~~text
1. compile-processor
   - build annotation API + annotation processor bằng JDK được hỗ trợ
   - bảo đảm processor thực sự nằm trên processor path

2. positive-type-use
   - compile GoodSample với -processor tường minh
   - kiểm exit code bằng 0 và output classes phù hợp

3. negative-type-use
   - compile BadSample với -processor tường minh
   - kiểm exit code khác 0 và có hai diagnostic có ý nghĩa

4. disabled-processing-canary
   - compile BadSample với -proc:none
   - xác nhận hành vi khác với negative-type-use

5. nested-and-cast
   - fixture generic lồng, wildcard, array nhiều chiều
   - AST/bytecode test riêng cho cast annotation nếu analyzer hỗ trợ

6. clean-and-incremental
   - xóa outputs trong môi trường test và compile sạch
   - test cập nhật generated files khi sửa input
   - so sánh với kết quả incremental ở công cụ build đang dùng

7. supported-jdk-matrix
   - chạy trên các toolchain thực sự được dự án hỗ trợ
   - kiểm build tool, JDK compiler API và processor dependencies
~~~

**Một nguyên tắc cực kỳ hữu ích:** Trong CI phải có ít nhất **một test cố ý sai nhưng chỉ sai khi processor chạy**. Nếu compile vẫn pass khi test này được kỳ vọng fail, đó là dấu hiệu processor/checker không được bật hoặc không quét đúng vị trí. Test này giúp tránh lỗi “processor bị bỏ qua nhưng cả pipeline vẫn xanh”.

### Kết quả nào phải báo cáo?

| Tình trạng | Kết luận hợp lý |
| --- | --- |
| Good pass, Bad fail với diagnostic mong đợi | Processor hoạt động cho các fixture đã kiểm |
| Good pass, Bad pass khi không có `-proc:none` | Có thể processor chưa chạy/không quét đúng vị trí; **không** kết luận pass |
| Good fail | Tooling/compiler config hoặc rule có vấn đề; điều tra diagnostic |
| Bad fail chỉ vì lỗi syntax khác | Chưa chứng minh processor phát hiện vi phạm chủ đích |
| Test cast pass nhưng chỉ biên dịch cú pháp | Chưa chứng minh analyzer thực sự đọc cast annotation |
| Clean pass, incremental fail | Nguy cơ stale cache/generated sources hoặc invalidation không đúng |

Không dùng một số liệu tổng hợp như “100% test pass” để che thiếu **negative fixtures** hoặc compiler invocation sai.

## 12. Lưu ý về module, build tools và độ an toàn

**Processor path khác application classpath.** Processor là code chạy **trong quá trình build**, không nhất thiết là dependency lúc ứng dụng chạy. Nếu dùng modules, kiểm riêng cơ chế tìm processor qua `--processor-module-path` (khi phù hợp) so với classpath `-processorpath`. Đừng vô tình đưa processor code vào runtime deployment chỉ vì muốn compiler nhìn thấy nó.

**Processor có thể chạy code tùy ý trong build process.** Chỉ dùng processor và plugin đã được tin cậy/đánh giá, pin version theo quy tắc dự án và kiểm provenance/dependency trong pipeline. Đây cũng là lý do việc bỏ implicit processor discovery từ JDK 23 đáng lưu ý.

**Không tắt warning/lỗi để “build xanh”.** Nếu processor báo diagnostics lỗi, điều tra fixture hoặc annotation contract. Dùng `Diagnostic.Kind.ERROR` cho vi phạm bắt buộc; warning chỉ phù hợp cho quy tắc mang tính khuyến nghị và cần CI policy rõ ràng.

**Đừng lạm dụng annotation processor để phân tích mọi thứ.** JSR 269 tốt để duyệt declarations/type model và sinh mã. Các phân tích đòi control flow, dataflow, path sensitivity, alias tracking, AST hoặc bytecode nên dùng công cụ tương ứng và có bộ test sâu hơn. Không trình bày processor ví dụ này như nullness analyzer hoàn chỉnh.

**Java 8 và hiện đại:** Package `javax.annotation.processing` là API Java compiler chuẩn còn sử dụng, **không phải** một thư viện Jakarta cần đổi package namespace. Những API như `com.sun.mirror.apt` (hệ xử lý chú thích Java rất cũ) không được dùng ở đây. Hãy tra đúng JDK/compiler version mà dự án hỗ trợ và tránh các cách cấu hình xử lý chú thích đã lỗi thời.

## 13. Lỗi hay gặp và cách sửa

| Lỗi | Nguyên nhân | Cách kiểm/sửa |
| --- | --- | --- |
| `@Mark` không phát lỗi ở BadSample | Processor chưa chạy hoặc chỉ quét declaration | Ép `-processor` và kiểm canary âm |
| Processor thấy field nhưng không thấy annotation | Nhãn ở nested type argument hoặc component | Duyệt `DeclaredType.getTypeArguments()`/`ArrayType.getComponentType()` |
| Cast annotation bị bỏ qua | Cast thuộc expression AST, không phải field element | Dùng Tree API hoặc bytecode analysis, có fixture riêng |
| Type annotation bị đọc như field declaration | Gọi `Element.getAnnotationMirrors()` ở sai node | Dùng `TypeMirror.getAnnotationMirrors()` tại đúng tầng |
| Processor chạy trên JDK cũ nhưng không chạy trên JDK mới | Trông chờ implicit discovery | Cấu hình processing explicit; kiểm JDK 23+ |
| Code processor báo warning source version | `@SupportedSourceVersion(RELEASE_8)` cứng khi chạy compiler mới | Chọn chính sách source version phù hợp toolchain |
| Diagnostic khó kiểm do locale/JDK | Match toàn bộ stderr | Kiểm exit code, `Kind.ERROR` và phần thông điệp ổn định |
| Build pass nhưng generated file cũ | Cache/incremental state không sạch | Bổ sung clean/incremental parity tests |
| Retention CLASS không đọc được qua reflection | Metadata không runtime-visible | Kiểm bytecode/processor hoặc dùng RUNTIME khi thực sự cần |
| Processor làm hỏng build khác | Claim `"*"` hoặc sinh file ngoài ý muốn | Không claim mọi annotation tùy tiện; giới hạn phạm vi và kiểm rounds |

## 14. Bài tập thực hành và đáp án định hướng

**Bài 1 — Canary processor.** Chạy lần lượt `GoodSample`, `BadSample` và `BadSample` với `-proc:none`. Kỳ vọng **pass / fail / pass**. Giải thích vì sao lần ba là chứng cứ việc kiểm tra đến từ processor.

**Bài 2 — Generic argument sai cấp.** Đổi `List<@Mark String>` thành `@Mark List<String>`. `javac` vẫn có thể cho phép cú pháp, nhưng processor ở mục 5 phải báo lỗi vì annotation không nằm trên **argument**. Giải thích bằng `DeclaredType.getTypeArguments()`.

**Bài 3 — Array sai cấp.** Đổi `String @Mark [] names;` thành `@Mark String[] names;`. Processor phải báo thiếu tag ở **outer array**, dù element type có tag. Kiểm lại bằng `ArrayType.getComponentType()`.

**Bài 4 — Nested generics.** Tạo `Map<String,List<@Mark Integer>>`. Viết một helper duyệt hai tầng `DeclaredType` và xác minh tìm được `@Mark` trên `Integer`.

**Bài 5 — Cast AST.** Tạo một fixture có `(@Mark String) raw` và một fixture không có tag. Dùng JDK Tree API, kiểm `TypeCastTree.getType()` và `AnnotatedTypeTree`. Giải thích vì sao `Field.getAnnotatedType()` không thể thay thế.

**Bài 6 — Retention.** Đổi `@Retention(CLASS)` thành `@Retention(RUNTIME)`. Đọc annotation ở field declaration/type qua reflection khi phù hợp, so sánh với thông tin processor. Vì sao đổi retention không khiến checker tự động chạy?

**Bài 7 — Two-round generation.** Thiết kế processor tạo một class Java trong round đầu bằng `Filer`. Kiểm round sau thấy class mới và round cuối không tạo file mới; kiểm không phát sinh `FilerException`.

**Bài 8 — Multi-processor.** Thêm processor khác chạy cùng build. Bảo đảm processor `"*"` không claim mọi annotation bằng `return true` và không phụ thuộc thứ tự discovery.

**Bài 9 — Build matrix.** Dùng JDK/toolchain được dự án hỗ trợ để chạy 4 test: positive, negative, disabled, clean. Giải thích tại sao processor ở classpath nhưng không có cấu hình processing explicit là một rủi ro ở JDK 23+.

**Bài 10 — Reviewer checklist.** Viết checklist có đủ target, retention, compiler/toolchain, processor activation, correct nested type path, cast AST, diagnostic kind, generated files, cache và negative tests. Định nghĩa evidence mà CI phải lưu khi có regression.

**Đạt yêu cầu khi:** bạn thực hiện được test dương/âm, biết vì sao `RoundEnvironment` không tự bao phủ mọi type-use, duyệt đúng `TypeMirror` trong generic/array, giải thích được cast cần AST/bytecode analysis, và không đánh đồng “annotation đã có” với “kiểm tra đã chạy”.

## 15. Tài liệu kỹ thuật chính thức đang còn áp dụng

- **Oracle Java SE 25 — javac:** https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- **Oracle Java SE 25 — javax.annotation.processing.Processor:** https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Processor.html
- **Oracle Java SE 25 — javax.annotation.processing.AbstractProcessor:** https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html
- **Oracle Java SE 25 — javax.lang.model.type.TypeMirror:** https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html
- **Oracle Java SE 25 — javax.lang.model.type.DeclaredType:** https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/DeclaredType.html
- **Oracle Java SE 25 — com.sun.source.util.Trees:** https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/Trees.html
- **Oracle Java SE 25 — com.sun.source.tree.TypeCastTree:** https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/TypeCastTree.html
- **OpenJDK/JDK 23 — thông báo đổi chính sách annotation processing mặc định:** https://inside.java/2024/06/18/quality-heads-up/
- **Java Language Specification — annotation locations, `9.7.4:** https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4

**Ghi nhớ:** Một bộ kiểm thử annotation processor đạt yêu cầu không chỉ “compile đúng source”. Nó phải chứng minh công cụ **được bật thật**, đọc **đúng vị trí TYPE_USE**, phát **diagnostic âm** ở fixture sai, và vận hành ổn định trong clean/incremental builds trên JDK còn được hỗ trợ.