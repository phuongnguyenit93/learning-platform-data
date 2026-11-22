# Visitor và duyệt mô hình theo loại phần tử

## 1. Bài toán: đọc một cấu trúc Java có nhiều loại khai báo

Trong annotation processing, trình biên dịch cung cấp mô hình **`javax.lang.model`** gồm nhiều dạng `Element`: module, package, class/interface/record, field, method, constructor, record component, type parameter... Một processor muốn kiểm tra hoặc sinh mã dựa trên các khai báo này phải trả lời hai câu hỏi:

1. **Gặp một phần tử thì xử lý thế nào theo loại phần tử đó?** Ví dụ `TypeElement` xử lý khác `ExecutableElement`.
2. **Làm sao đi từ một phần tử gốc xuống những phần tử bên trong?** Ví dụ từ record xuống record components, field, constructor, method; từ method xuống tham số.

Java có sẵn hai dạng công cụ cần phân biệt:

- **Visitor** triển khai `ElementVisitor<R, P>` và được một `Element` gọi qua `accept(visitor, parameter)`. Visitor **phân nhánh theo loại element**; tự nó **không mặc định duyệt đệ quy mọi phần tử con**.
- **Scanner** như `ElementScanner14<R,P>` vừa là visitor vừa có các phương thức `scan(...)` và các `visitXyz(...)` tự duyệt những phần tử liên quan theo hợp đồng của scanner. Scanner phù hợp khi cần **traversal** qua cây khai báo.

Điểm mấu chốt: **Visitor quyết định làm gì tại một node; Scanner quyết định làm gì tại node và có thể đi tiếp đến các node bên trong.**

~~~text
RoundEnvironment.getElementsAnnotatedWith(@Inspect)
                 |
                 v
            Element gốc
                 |
        +--------+--------+
        |                 |
        v                 v
 element.accept(...)   scanner.scan(...)
        |                 |
   dispatch tới      dispatch tới visitXyz
     visitType             |
      ...                 v
                    scan enclosed elements
                          |
                    +-----+-----+
                    |           |
              visitExecutable  visitRecordComponent
                    |           |
                 scan params    scan enclosed
~~~

Đây là **mô hình khai báo**, không phải AST của các biểu thức/câu lệnh Java. Scanner không tự đi vào nội dung từng `if`, `return`, phép gọi method hay nhánh trong method body. Khi cần duyệt AST, dùng Compiler Tree API (`com.sun.source.tree`/`Trees`, thuộc `jdk.compiler`) cùng chính sách riêng.

## 2. Hiểu đúng `ElementVisitor<R,P>` và `Element.accept(...)`

Giao diện trung tâm là `javax.lang.model.element.ElementVisitor<R,P>`. Hai tham số generic có ý nghĩa:

- **`R`:** kiểu giá trị trả về từ các `visitXyz`. Ví dụ `String` cho mô tả node, `Boolean` cho kiểm tra, hoặc `Void` nếu chỉ ghi nhận thông tin.
- **`P`:** kiểu dữ liệu bổ sung truyền vào mỗi lần visit. Ví dụ cấu hình, danh sách cảnh báo, mức thụt dòng hoặc đối tượng context; dùng `Void` nếu không cần.

Các phương thức tiêu biểu:

~~~java
R visitType(TypeElement e, P p);
R visitExecutable(ExecutableElement e, P p);
R visitVariable(VariableElement e, P p);
R visitRecordComponent(RecordComponentElement e, P p);
R visitPackage(PackageElement e, P p);
R visitModule(ModuleElement e, P p);
R visitTypeParameter(TypeParameterElement e, P p);
R visitUnknown(Element e, P p);
~~~

Các chữ ký trên là **trích yếu API**, không phải một interface Java hoàn chỉnh để copy biên dịch. `ElementVisitor` còn có các overload `visit(...)` và phương thức cần thiết khác.

Với một đối tượng `Element e`:

~~~java
String label = e.accept(myVisitor, null);
~~~

Compiler model sẽ dispatch lời gọi sang method thích hợp của visitor, chẳng hạn `visitType(TypeElement, P)` khi `e` là một type declaration. Ta cũng có thể dùng `myVisitor.visit(e)` vì các lớp visitor nền cung cấp phương thức tiện ích tương ứng.

**Đừng dùng `instanceof` trên implementation class của model để phân loại tất cả node.** JavaDoc của `Element` lưu ý một implementation có thể chọn cách một object thực hiện nhiều interface. Sử dụng visitor và/hoặc `getKind()` là cách làm được thiết kế riêng cho mô hình này.

### 2.1. Dispatch theo interface không hoàn toàn giống `ElementKind`

`visitType(TypeElement, P)` được gọi cho nhiều loại khai báo type như `CLASS`, `INTERFACE`, `ENUM`, `ANNOTATION_TYPE`, **`RECORD`**. Không có phương thức `visitRecord(TypeElement,...)` trong `ElementVisitor`.

Để biết cụ thể type có phải record:

~~~java
@Override
public String visitType(TypeElement e, Void p) {
    return e.getKind() == ElementKind.RECORD ? "RECORD" : "OTHER_TYPE";
}
~~~

Đây là **snippet bên trong subclass của `SimpleElementVisitor14<String,Void>`**, cần import `ElementKind`, `TypeElement`. Trong chương trình đầy đủ bên dưới, visitor tương tự trả `e.getKind().name()`.

Nếu cần dispatch theo từng **giá trị `ElementKind`** thay vì từng interface `Element`, `ElementKindVisitor14<R,P>` cung cấp các nhánh kiểu `visitTypeAsRecord(...)`, `visitTypeAsClass(...)`, `visitVariableAsField(...)`. Đây là một lựa chọn khác; không nhầm với `ElementScanner14` tự duyệt đệ quy.

## 3. Các họ visitor và scanner nên chọn thế nào?

| Lớp/API | Hành vi mặc định | Dùng khi |
| --- | --- | --- |
| `ElementVisitor<R,P>` | Hợp đồng visit, không triển khai traversal | Muốn định nghĩa toàn bộ visitor theo nhu cầu |
| `SimpleElementVisitor14<R,P>` | Phần lớn `visitXyz` gọi `defaultAction(...)` | Muốn **xử lý một node** với một vài override |
| `ElementKindVisitor14<R,P>` | Phân nhánh theo `ElementKind` cụ thể | Muốn khác biệt giữa record/class/interface hoặc field/parameter |
| `ElementScanner14<R,P>` | Tự scan các phần tử con theo các `visitXyz` | Muốn **đi từ root qua cây khai báo** |
| `ElementFilter` | Lọc collection element theo kind (methods, fields, types, record components...) | Chỉ cần lấy một loại thành viên, chưa cần visitor riêng |
| `TypeVisitor<R,P>` / `SimpleTypeVisitor14`, `TypeKindVisitor14` | Duyệt **`TypeMirror`**, không phải `Element` | Muốn phân biệt declared type, array, wildcard, type variable... |

`SimpleElementVisitor14` và `ElementScanner14` là các API **hiện hành** có hỗ trợ record, dùng được trên Java 17+. Con số `14` là tên thế hệ visitor, **không có nghĩa** bạn phải bật Java 14 preview feature. Record đã là tính năng chính thức của Java từ Java 16.

Khi muốn tạo processor chạy Java 17+ và cần record components, dùng `*Visitor14` / `*Scanner14` là lựa chọn tương thích. Với feature Java mới hơn xuất hiện trong các phiên bản sau, phải xem JavaDoc của loại visitor được chọn và kiểm thử khi nâng JDK; đừng mặc định visitor cũ sẽ xử lý tất cả element kind chưa tồn tại lúc nó được thiết kế. Các lớp `*Preview` không phải mặc định phù hợp cho tài liệu/mã sản xuất không sử dụng preview.

### 3.1. `SimpleElementVisitor14`: một nhánh xử lý và fallback

Một subclass nhỏ:

~~~java
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.SimpleElementVisitor14;

final class TypeNameVisitor extends SimpleElementVisitor14<String, Void> {
    TypeNameVisitor() {
        super("NOT_A_TYPE");
    }

    @Override
    public String visitType(TypeElement type, Void ignored) {
        return type.getQualifiedName().toString();
    }
}
~~~

Class `TypeNameVisitor` là **mẫu có thể đặt vào dự án Java** (cần gọi từ chương trình/compiler processing context), không phải ứng dụng có `main`. `super("NOT_A_TYPE")` đặt giá trị của `defaultAction` cho các loại element chưa override. Không có traversal: gọi `e.accept(new TypeNameVisitor(), null)` trên một `TypeElement` chỉ trả mô tả type ấy, **không tự động visit từng method/field trong type**.

`SimpleElementVisitor14` có `visitRecordComponent(...)` hỗ trợ component của record. Nếu không override, nó gọi `defaultAction(...)` như các loại đã biết khác. Với loại khai báo tương lai mà visitor hiện tại chưa biết, hành vi `visitUnknown(...)` cần được xem xét (có thể dẫn đến `UnknownElementException` nếu giữ hành vi mặc định).

### 3.2. `ElementScanner14`: visitor có traversal mặc định

`ElementScanner14` mở rộng dãy `ElementScanner6/7/8/9`, thêm hành vi dành cho record và các phần tử tương ứng. Nó có:

~~~java
R scan(Element element, P p);
R scan(Iterable<? extends Element> elements, P p);
R scan(Element element);  // tương đương scan(element, null)
~~~

Đây là **các chữ ký API rút gọn**. `scan(element,p)` gọi `element.accept(this,p)`; các override `visitXyz(...)` có thể gọi `super.visitXyz(e,p)` để tiếp tục duyệt.

Hành vi quan trọng của scanner:

- `visitType`: duyệt các type parameters (nếu có), sau đó các phần tử được chứa bên trong type.
- `visitExecutable`: duyệt type parameters của method/constructor (nếu có), sau đó các tham số.
- `visitRecordComponent`: duyệt các phần tử được chứa trong record component theo model.
- `visitPackage` / `visitModule`: duyệt những phần tử phù hợp theo hợp đồng scanner và môi trường model.
- `scan(Iterable,...)`: lần lượt visit các element trong iterable được truyền vào.

**Cảnh báo phạm vi:** `scan(packageElement)` hoặc `scan(moduleElement)` có thể duyệt rất nhiều phần tử, không phù hợp khi processor chỉ cần một tập class có annotation. Hãy bắt đầu từ tập root hẹp do `RoundEnvironment.getElementsAnnotatedWith(...)` cung cấp.

**Cảnh báo kết quả:** phương thức `scan(Iterable,...)` không tự động gộp `R` theo quy tắc cộng/list. Với bài toán thống kê, thường dùng `Void` và một collector/danh sách thuộc visitor instance (hoặc dữ liệu context `P`). Khi cần phép tổng hợp giá trị `R`, tự thiết kế phép gộp thay vì dựa vào kết quả trả về mặc định.

## 4. Gọi `super.visitXyz(...)` quyết định bạn có đi tiếp hay không

Một override ở scanner có thể làm công việc **trước khi duyệt con**:

~~~java
@Override
public Void visitType(TypeElement type, Void p) {
    lines.add("TYPE " + type.getQualifiedName());
    return super.visitType(type, p);
}
~~~

Đây là **snippet thuộc một subclass của `ElementScanner14<Void,Void>`** với field `List<String> lines`. Lời gọi `super.visitType(type,p)` quan trọng vì nó tiếp tục scan type parameters và các phần tử bên trong type.

Ngược lại, nếu override như sau:

~~~java
@Override
public Void visitType(TypeElement type, Void p) {
    lines.add("TYPE " + type.getQualifiedName());
    return null;
}
~~~

Scanner sẽ ghi type ấy nhưng **không tự duyệt các thành phần con từ lời gọi này**. Điều này có thể là chủ ý khi cần dừng tại ranh giới một type; nếu không phải chủ ý, đó là lỗi làm mất dữ liệu trong quá trình traversal.

Nếu muốn duyệt **hậu tự** (postorder), có thể đặt công việc xử lý **sau** `super.visitType(type,p)`:

~~~java
@Override
public Void visitType(TypeElement type, Void p) {
    super.visitType(type, p);
    lines.add("DONE " + type.getQualifiedName());
    return null;
}
~~~

Cả ba đoạn là **minh họa về điều khiển traversal**, không phải ba bản hoàn chỉnh của cùng một class. Lựa chọn tiền tự/hậu tự có ý nghĩa khi sinh mã phụ thuộc vào các thành viên bên trong.

Một ví dụ dùng `P` để truyền **độ sâu**:

~~~java
final class DepthScanner extends ElementScanner14<Void, Integer> {
    @Override
    public Void visitType(TypeElement type, Integer depth) {
        System.out.println(" ".repeat(depth) + type.getSimpleName());
        return super.visitType(type, depth + 1);
    }
}
// Trong processor: new DepthScanner().scan(rootType, 0);
~~~

Đây là snippet có thể nhúng vào processor (cần import `ElementScanner14`, `TypeElement`). `P` giúp truyền context dọc theo lời gọi scan; nhưng không mặc định biến mọi node thành một tầng thụt thêm trừ khi các override liên quan tăng depth đúng lúc. Dùng `System.out` ở đây để diễn giải; **processor thật nên dùng `Messager`** để ghi diagnostic.

## 5. Nên quét root nào và bằng cách nào?

Có ba điểm bắt đầu phổ biến:

1. **Annotated roots:** `round.getElementsAnnotatedWith(SomeAnnotation.class)`. Hữu ích khi chỉ cần các khai báo gắn annotation; giới hạn phạm vi và dễ tránh scan cả module.
2. **Root elements của round:** `round.getRootElements()`. Hữu ích khi cần quan sát những đơn vị biên dịch xuất hiện ở round hiện tại; không tự coi đó là “mọi class/JAR trong project”.
3. **Type tra cứu từ `Elements`:** `processingEnv.getElementUtils().getTypeElement("a.b.C")`. Hữu ích khi cần một khai báo cụ thể từ source/classpath/module path; kiểm tra `null` trước khi scan.

Trong annotation processing có nhiều round, **cùng một processor có thể nhận nhiều lời gọi `process(...)`**. Nếu tổng hợp toàn batch, phải quản lý chuyện một element có thể cần được xét riêng ở nhiều thời điểm và chặn việc sinh resource trùng. Với ví dụ ở mục 7, processor chỉ phát diagnostic cho annotated roots của round hiện tại, không sinh mã, nên logic đơn giản hơn.

**Không giả định `ElementScanner14` tự đi theo mọi cạnh của type graph.** Duyệt **nested declarations** khác với duyệt các **supertype** hoặc type arguments. Nếu muốn truy vết cấu trúc thừa kế/generic, hãy lấy `TypeMirror`, dùng `Types.directSupertypes(...)`, `getDeclaredType(...)` hoặc `TypeVisitor` với thuật toán riêng. Đừng dùng scanner cây khai báo như một thuật toán duyệt toàn bộ đồ thị kiểu.

## 6. Ví dụ Java 17+ hoàn chỉnh: visitor xác định root và scanner kiểm tra cấu trúc record

Ta xây dựng một annotation processor `ModelVisitorProcessor` làm hai công việc:

- **`RootLabel extends SimpleElementVisitor14<String,Void>`**: xử lý **một root**, trả `RECORD` khi khai báo là record hoặc trả `CLASS` khi là class. Đối với root khác, trả giá trị `OTHER`.
- **`DetailScanner extends ElementScanner14<Void,Void>`**: đi vào record, thu tên type, các record component và một method `summary()`. Các mục được sắp xếp để diagnostic có thứ tự xác định.
- Processor từ chối `@ShowModel` đặt trên class thông thường bằng `ERROR` và chấp nhận record bằng `NOTE`.

Bài này minh họa đồng thời **visitor = dispatch** và **scanner = traversal** trên mô hình khai báo thật, **không** đi vào method body.

### 6.1. Cấu trúc thư mục

~~~text
visitor-demo/
└── src/
    └── demo/
        ├── ShowModel.java
        ├── ModelVisitorProcessor.java
        ├── Invoice.java
        └── InvalidType.java
~~~

Các thư mục `build/processor` và `build/classes` sẽ được tạo ở bước chạy lệnh.

### 6.2. Annotation: `src/demo/ShowModel.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface ShowModel {}
~~~

Annotation có `@Target(TYPE)` nên có thể gắn lên một type declaration; processor **giới hạn thêm** rằng chỉ record mới được gắn annotation này. `RetentionPolicy.SOURCE` phù hợp với metadata chỉ cần tại thời điểm compile.

### 6.3. Processor đầy đủ: `src/demo/ModelVisitorProcessor.java`

~~~java
package demo;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.RecordComponentElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementScanner14;
import javax.lang.model.util.SimpleElementVisitor14;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.ShowModel")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelVisitorProcessor extends AbstractProcessor {
    private static final class RootLabel
            extends SimpleElementVisitor14<String, Void> {
        RootLabel() {
            super("OTHER");
        }

        @Override
        public String visitType(TypeElement e, Void unused) {
            return e.getKind().name();
        }
    }

    private static final class DetailScanner
            extends ElementScanner14<Void, Void> {
        private final List<String> lines = new ArrayList<>();

        @Override
        public Void visitType(TypeElement e, Void unused) {
            lines.add("TYPE " + e.getQualifiedName() + ":" + e.getKind());
            return super.visitType(e, unused);
        }

        @Override
        public Void visitRecordComponent(
                RecordComponentElement e, Void unused) {
            lines.add("COMPONENT " + e.getSimpleName() + ":" + e.asType());
            return super.visitRecordComponent(e, unused);
        }

        @Override
        public Void visitExecutable(ExecutableElement e, Void unused) {
            if (e.getKind() == ElementKind.METHOD
                    && e.getSimpleName().contentEquals("summary")) {
                lines.add("METHOD summary:" + e.getReturnType());
            }
            return super.visitExecutable(e, unused);
        }

        List<String> results() {
            Collections.sort(lines);
            return lines;
        }
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        for (Element element :
                round.getElementsAnnotatedWith(ShowModel.class)) {
            String rootKind = element.accept(new RootLabel(), null);
            if (!"RECORD".equals(rootKind)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@ShowModel needs a record", element);
                continue;
            }

            DetailScanner scanner = new DetailScanner();
            scanner.scan(element);
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE, "ROOT " + rootKind, element);
            for (String line : scanner.results()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE, "VISIT " + line, element);
            }
        }
        return true;
    }
}
~~~

**Giải thích chi tiết:**

- `RootLabel` không duyệt con. `element.accept(new RootLabel(), null)` gửi phần tử gốc tới `visitType` nếu đó là một `TypeElement`; method trả `e.getKind().name()`. Một record trả `RECORD`, class thường trả `CLASS`.
- `new RootLabel()` tạo visitor **cho một lần dispatch**. Nó có `super("OTHER")` để các loại element khác nhận fallback `OTHER`.
- `DetailScanner.scan(element)` mới là bước **traversal**. Khi gặp record gốc, `visitType` của scanner ghi một dòng TYPE rồi gọi `super.visitType(...)` để đi vào các member.
- `visitRecordComponent` bắt các component như `code` và `quantity`, ghi đúng kiểu `String` / `int` của chúng. `super.visitRecordComponent(...)` giữ logic quét các phần tử bên trong nếu model cung cấp.
- `visitExecutable` được gọi cho các method/constructor mà scanner chạm tới. Vì chỉ cần method `summary()`, ví dụ lọc rõ `ElementKind.METHOD` và tên `summary`; không dựa vào việc compiler có bao nhiêu method/accessor/constructor được sinh hoặc hiển thị.
- `Collections.sort(lines)` chỉ thay đổi **thứ tự báo cáo**, không làm thay đổi thứ tự thực tế mà scanner đã duyệt. Nhờ đó output mô tả ổn định và dễ kiểm thử.
- `Messager.printMessage(..., element)` gắn diagnostic vào khai báo gốc trong file nguồn. `Diagnostic.Kind.NOTE` cho phép compile tiếp; `ERROR` khiến case sai không vượt qua build.
- `@SupportedSourceVersion(RELEASE_17)` nhất quán với `javac --release 17` trong phần thực hành. `return true` nghĩa là processor claim annotation đã nhận, **không phải** xác nhận tất cả case hợp lệ.

### 6.4. Record hợp lệ: `src/demo/Invoice.java`

~~~java
package demo;

@ShowModel
public record Invoice(String code, int quantity) {
    public String summary() {
        return code + "=" + quantity;
    }

    public static void main(String[] args) {
        System.out.println(new Invoice("A1", 3).summary());
    }
}
~~~

Record có hai component và một method `summary()` do tác giả khai báo. Method `main(...)` chỉ để chứng minh chương trình đích đã biên dịch xong và có thể chạy. Processor không mở hoặc phân tích body của method `summary()`.

### 6.5. Type sai để kiểm thử: `src/demo/InvalidType.java`

~~~java
package demo;

@ShowModel
public class InvalidType {
}
~~~

`@ShowModel` được phép gắn lên type theo `@Target(TYPE)`, nhưng processor quy định **phải là record**. Vì vậy source này sẽ bị chặn bởi `ModelVisitorProcessor`.

### 6.6. Biên dịch processor và chạy test thành công

Từ thư mục gốc `visitor-demo`, trên Linux/macOS tạo các thư mục:

~~~sh
mkdir -p build/processor build/classes
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/processor,build/classes | Out-Null
~~~

Sau đó dùng cùng bộ lệnh trên các hệ điều hành (đường dẫn chỉ có một directory cho mỗi option):

~~~sh
javac --release 17 -d build/processor src/demo/ShowModel.java src/demo/ModelVisitorProcessor.java
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ModelVisitorProcessor -d build/classes src/demo/Invoice.java
java -cp build/classes demo.Invoice
~~~

**Vì sao phải chia thành hai lần compile?** Compiler cần nạp class processor `demo.ModelVisitorProcessor` **trước** khi xử lý `@ShowModel` trên `Invoice`. Đầu tiên biên dịch annotation/processor vào `build/processor`; lần sau đặt chúng trong classpath và processor path, rồi bật processor bằng `-processor demo.ModelVisitorProcessor`.

Bước `javac` thứ hai phát các **nội dung diagnostic NOTE** theo thứ tự sau (đã kiểm thử bằng JDK 24):

~~~text
ROOT RECORD
VISIT COMPONENT code:java.lang.String
VISIT COMPONENT quantity:int
VISIT METHOD summary:java.lang.String
VISIT TYPE demo.Invoice:RECORD
~~~

Đây là **message của từng diagnostic**, không phải toàn bộ stdout byte-for-byte của lệnh `javac`. Công cụ build/JDK/IDE có thể in thêm đường dẫn tệp, số dòng, tiền tố `Note:` hoặc dấu caret. Các dòng được sắp xếp theo `Collections.sort`, vì vậy thứ tự nội dung diagnostic trong processor là xác định.

**Stdout chính xác** của lệnh `java -cp build/classes demo.Invoice`:

~~~text
A1=3
~~~

Điều này xác nhận processor đã chạy khi build nhưng chương trình `Invoice` chạy sau đó không cần bản thân processor để thực thi logic record.

### 6.7. Test lỗi: một type được visitor nhận diện nhưng bị từ chối

Chạy riêng (không gộp với test thành công):

~~~sh
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ModelVisitorProcessor -d build/classes src/demo/InvalidType.java
~~~

Lệnh **được kỳ vọng thất bại** với exit code khác `0`. Diagnostic chứa:

~~~text
error: @ShowModel needs a record
~~~

Trên terminal, compiler có thể in đường dẫn file và caret ngoài phần message trên. Đây không phải output từ chương trình `java`, mà là compiler diagnostic của test âm tính. Đã xác minh thực tế rằng case này bị processor chặn và `javac` trả trạng thái lỗi.

## 7. Duyệt theo loại phần tử nhưng tránh phụ thuộc quá mức vào cấu trúc ngầm

Trong source Java, trình biên dịch có thể tạo ra những phần tử **ngầm định** hoặc thể hiện member theo quy tắc mô hình. Ví dụ record có accessor, field và constructor liên quan đến component. Nếu viết processor như:

~~~java
for (Element member : record.getEnclosedElements()) {
    System.out.println(member.getKind() + " " + member.getSimpleName());
}
~~~

thì số lượng/phân bố các phần tử được thấy có thể không giống việc **đếm dòng khai báo mà lập trình viên tự gõ**. Vì vậy demo **chỉ lọc method có tên `summary`** và xử lý record components bằng visitor riêng.

**`getEnclosedElements()` không đồng nghĩa `getAllMembers()`.** Scanner mặc định đi theo quan hệ bao chứa, trong khi `Elements.getAllMembers(TypeElement)` dùng khi cần **các member thừa kế**, không chỉ khai báo bên trong. Nếu yêu cầu là kiểm tra mọi public method của một interface được implements, chỉ scan enclosed members có thể bỏ sót inherited methods.

Nếu thực sự cần chỉ các record components và không cần visitor traversal phức tạp, dùng trực tiếp:

~~~java
for (RecordComponentElement c : record.getRecordComponents()) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.NOTE,
            c.getSimpleName() + ":" + c.asType(), c);
}
~~~

Đây là **snippet trong processor**, với `record` là `TypeElement` đã xác nhận có `ElementKind.RECORD`. Chọn con đường đơn giản nhất đáp ứng mục tiêu: visitor/scanner phù hợp khi có nhiều loại element và cần một chính sách duyệt nhất quán, không bắt buộc chỉ vì dự án dùng annotation processing.

## 8. Khác biệt giữa `ElementVisitor` và `TypeVisitor`

Mô hình compiler có **hai họ mô hình**:

- `Element` / `ElementVisitor`: những **khai báo** như class, record, method, field, package, module.
- `TypeMirror` / `TypeVisitor`: những **kiểu** như primitive `int`, array `String[]`, declared type `List<String>`, type variable `T`, wildcard `? extends Number`.

Chẳng hạn trong processor:

~~~java
TypeMirror type = element.asType();
TypeKind kind = type.getKind();
~~~

Đây là **snippet** với các import `javax.lang.model.type.TypeMirror` và `TypeKind`; chỉ dùng khi `element` có ý nghĩa kiểu tương ứng. Không dùng `ElementVisitor.visitType(...)` để xử lý từng type argument generic — đó là bài toán của `TypeMirror`/`TypeVisitor`, `DeclaredType.getTypeArguments()` và các phép toán `Types`.

Nếu muốn visitor cho model kiểu, có các lớp:

- `SimpleTypeVisitor14<R,P>`: default action cho type model.
- `TypeKindVisitor14<R,P>`: dispatch chi tiết theo `TypeKind`.
- `Types`: so sánh/suy luận quan hệ ngữ nghĩa như `isSameType`, `isAssignable`, `isSubtype`, `erasure`, `asMemberOf`.

**Tuyệt đối không so sánh `TypeMirror` bằng cách parse chuỗi `toString()` để xác nhận quan hệ kiểu.** Dùng `Types`. Visitor/scanner chỉ mô tả **cách phân công xử lý và duyệt**, không thay thế kiểm tra type-safe theo quy tắc của ngôn ngữ Java.

## 9. Khi nào nên dùng `ElementFilter` thay visitor/scanner?

`ElementFilter` là tập tiện ích để lấy một subset của `Iterable<? extends Element>`. Nếu mục tiêu chỉ là “lấy các method trong class”, có thể làm:

~~~java
List<ExecutableElement> methods =
        ElementFilter.methodsIn(type.getEnclosedElements());
~~~

Đoạn trên là **snippet trong processor** với `type` là `TypeElement`; cần import `java.util.List`, `ExecutableElement`, `ElementFilter`. Nó chỉ lọc **input được truyền vào**. Nếu `type.getEnclosedElements()` chỉ chứa thành viên khai báo trực tiếp, `methodsIn(...)` không tự đi qua member được kế thừa hoặc qua tất cả nested type.

| Mục tiêu | Cách làm thường phù hợp |
| --- | --- |
| Chỉ lấy các method/field trong một type | `ElementFilter.methodsIn/fieldsIn(...)` |
| Chỉ lấy record component của một record | `TypeElement.getRecordComponents()` |
| Xử lý **một element** theo loại interface | `SimpleElementVisitor14` |
| Xử lý **một element** theo `ElementKind` cụ thể | `ElementKindVisitor14` |
| Duyệt cả cây declaration, có tiền tự/hậu tự | `ElementScanner14` |
| Duyệt/kiểm tra cấu trúc generic, type argument | `TypeVisitor` + `Types` |
| Phân tích biểu thức/câu lệnh Java | Compiler Tree API, không phải `ElementScanner14` |

Một processor có thể kết hợp các cách này. Ví dụ dùng scanner tìm các `TypeElement` lồng nhau rồi dùng `ElementFilter.methodsIn(...)` trên từng type, trong khi `Types.isAssignable(...)` kiểm tra kiểu hợp đồng.

## 10. Gắn context và thu kết quả khi traversal lớn hơn

### 10.1. `P` cho context, `R` cho kết quả

Giả sử muốn tạo báo cáo JSON cho nhiều type lồng nhau, có thể dùng:

- `P = TraversalContext` với thông tin root, stack, trạng thái depth hoặc tuỳ chọn xử lý.
- `R = Void` khi scanner đẩy từng thông tin vào một collector có ownership rõ ràng.
- `R = Result` khi viết visitor tự tổng hợp kết quả từ các node.

Nếu dùng `ElementScanner14<R,P>` mặc định, **không tự giả định phương thức scan của collection cộng hoặc merge nhiều `R`**. Việc tổng hợp phải do code ứng dụng định nghĩa. Với thống kê xuyên các node, danh sách/map accumulator thường rõ ràng hơn.

### 10.2. Không bỏ quên đường quay lại và phạm vi

Đối với scan sâu, nên có quy tắc rõ lúc nào vào type, lúc nào thoát. Ví dụ:

~~~java
@Override
public Void visitType(TypeElement type, VisitContext context) {
    context.enter(type);
    try {
        return super.visitType(type, context);
    } finally {
        context.exit(type);
    }
}
~~~

Đây là **snippet thiết kế**: `VisitContext` là **kiểu do ứng dụng tự định nghĩa** chứa `enter/exit`, không phải class API Java có sẵn. Mẫu `try/finally` minh họa cách cân bằng context khi scan gặp ngoại lệ. Nếu không có nhu cầu theo dõi stack/phạm vi, không cần tạo cấu trúc này.

### 10.3. Duyệt có chọn lọc

Nếu muốn bỏ qua nested class khi chỉ tính member **của root**, có thể kiểm tra `e.getEnclosingElement()` và quyết định **không gọi `super.visitType(...)` trên type không thuộc phạm vi cần duyệt**. Ngược lại, khi muốn scan toàn bộ nested type, phải gọi `super.visitType(...)` để scanner tiếp tục xuống dưới.

Việc lọc quá sớm theo tên `toString()` có thể bỏ qua các trường hợp nested/anonymous. Dùng `ElementKind`, `NestingKind`, `getEnclosingElement()` và `Elements.getBinaryName(...)` khi cần xác định danh tính/quan hệ.

## 11. Quản lý nhiều round và vòng đời processor

Annotation processor chạy qua một hoặc nhiều round. `RoundEnvironment.getElementsAnnotatedWith(...)` chỉ trả các phần tử phù hợp với **round hiện tại**; nó không mặc định là mọi class của toàn bộ project qua mọi phiên biên dịch.

Các lưu ý:

1. `AbstractProcessor.init(ProcessingEnvironment)` được gọi trước `process(...)`; dùng nó nếu cần lưu `Elements`, `Types`, `Filer` hoặc options cho phiên xử lý.
2. `process(...)` có thể chạy nhiều lần; tạo scanner **riêng mỗi root hoặc round** nếu collector cần tách dữ liệu. Demo dùng `new DetailScanner()` cho từng root.
3. `round.processingOver()` báo round cuối; không cố sinh thêm mã chỉ để mở một round khác.
4. Khi sinh source bằng `Filer.createSourceFile(...)`, trình biên dịch có thể tạo round mới; không được tạo cùng một output FQN nhiều lần trong một processing run.
5. `return true` nghĩa là processor **claim annotation types** được cung cấp; không bảo đảm task đã hoàn tất hoặc không có lỗi.
6. Không cache `Element` hoặc `TypeMirror` từ compiler session cũ vào biến static dùng xuyên các lần compile; model có vòng đời gắn với compilation environment.
7. Đừng scan toàn bộ root package/module mỗi round nếu chỉ muốn một annotation cụ thể: có thể trùng kết quả và tốn chi phí.

**Kích hoạt processor hiện nay:** từ JDK 23, annotation processing không nên được giả định tự bật chỉ vì có processor trong classpath. Khai báo rõ `-processor` và processor path/module path hoặc cấu hình build tool tương ứng. Ví dụ dùng `-processor demo.ModelVisitorProcessor` nên ổn định với cách kích hoạt mới.

## 12. Tương thích JDK và các `*Visitor14`

Những lớp có hậu tố số trong package `javax.lang.model.util` đã tồn tại qua nhiều phiên bản Java, tương ứng với mức ngôn ngữ mà chúng biết cách xử lý mặc định.

- **`SimpleElementVisitor14`, `ElementScanner14`, `ElementKindVisitor14`** là các API phù hợp với phần tử `RECORD`/`RECORD_COMPONENT`, dùng được trên Java 17+.
- **`SimpleElementVisitor9`, `ElementScanner9`** không phải lựa chọn tốt khi processor cần xử lý record components một cách đầy đủ và đúng mặc định.
- Một phần tử mới trong tương lai có thể không có branch tương ứng ở visitor cũ; hành vi mặc định của `visitUnknown(...)` có thể phát sinh `UnknownElementException`. Nếu cần nâng mức Java, kiểm thử đúng kinds/features mà dự án dùng, cân nhắc mở rộng visitor mới khi API hỗ trợ.
- **`*VisitorPreview` / `*ScannerPreview`** là API preview, không nên dùng cho ví dụ Java 17+ thông thường hoặc làm nền phụ thuộc lâu dài khi yêu cầu chỉ sử dụng tính năng ổn định.
- Chọn `@SupportedSourceVersion(SourceVersion.RELEASE_17)` khi processor ví dụ chỉ cam kết xử lý source Java 17. Với dự án dùng source release mới hơn, cần cập nhật mục tiêu kiểm thử và khai báo support; không chỉ đổi annotation một cách máy móc.

Đừng nhầm “visitor hậu tố 14” với “chỉ hoạt động trên JDK 14”. Hậu tố phản ánh **dòng visitor hỗ trợ các cấu trúc ngôn ngữ**, không phải yêu cầu dùng JDK 14 để chạy. Trên JDK 17, record là tính năng chính thức, không phải preview.

## 13. Những lỗi phổ biến

1. **Dùng `SimpleElementVisitor14` rồi nghĩ nó tự quét hết cây:** class này gọi `defaultAction` và chỉ xử lý node được visit. Muốn traversal hãy dùng `ElementScanner14` hoặc tự gọi scan.
2. **Override `visitType` của scanner nhưng quên `super.visitType(...)`:** cắt mất đường đi đến member/nested type. Chỉ bỏ `super` nếu bạn chủ ý dừng scan.
3. **Dùng `visitType` để phân biệt trực tiếp record và class mà không xem `getKind()`:** cả hai đều là `TypeElement`. Dùng `ElementKind.RECORD` hoặc `ElementKindVisitor14.visitTypeAsRecord`.
4. **Nhầm `RecordComponentElement` với `VariableElement` field:** record component có model riêng. `visitRecordComponent` không phải `visitVariable`.
5. **Quét toàn bộ package/module không giới hạn:** phạm vi lớn, tốn tài nguyên và dễ lặp trong nhiều round. Chọn annotated roots hoặc một type cụ thể.
6. **Dùng kết quả `scan(Iterable)` như thể đã gộp mọi node:** scanner không tự aggregate. Dùng collector hoặc viết phép gộp rõ ràng.
7. **Dùng `ElementScanner14` để tìm subtype hoặc generic theo graph:** scanner đi theo quan hệ declaration containment, không tự đi theo tất cả `Types.directSupertypes` hoặc type arguments.
8. **Không phân biệt declared members và inherited members:** `getEnclosedElements` không thay cho `Elements.getAllMembers`.
9. **Đếm mọi method của record bằng một số cố định:** compiler model có các member liên quan đến record, cả một số được sinh/implicit; hãy lọc theo hợp đồng cần kiểm tra.
10. **Không bảo vệ trường hợp unknown element trên JDK mới:** test và cập nhật visitor theo feature mới, hoặc xử lý `visitUnknown` có chủ đích.
11. **So sánh kiểu từ `toString()`:** muốn type-safe hãy dùng `Types`, không parse tên.
12. **Dùng reflection trên lớp đang được biên dịch:** đối tượng model chưa chắc có class đã load được trong JVM processor.
13. **Dùng `System.out` làm kênh lỗi compiler:** hãy dùng `Messager.printMessage(ERROR, ..., element)` để IDE/CI chỉ ra vị trí source.
14. **Processor không chạy do thiếu kích hoạt tường minh:** cấu hình `-processor`/`-processorpath` hoặc build tool annotation processing rõ ràng.

## 14. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Cần một function nhận `Element` và trả tên kiểu của nó, không duyệt con. Nên chọn gì?

**Đáp:** `SimpleElementVisitor14<String,Void>` với `visitType(...)`, kết hợp `element.accept(visitor, null)`. Chỉ cần visitor, không phải scanner.

**Câu 2.** Vì sao override `ElementScanner14.visitType(...)` không gọi `super.visitType(...)` lại làm mất các record components và methods bên trong?

**Đáp:** Vì phần traversal của `ElementScanner14` nằm trong `super.visitType(...)`. Khi không gọi nó, override xử lý root nhưng dừng tại đó.

**Câu 3.** `@ShowModel` gắn lên class thường, vậy `visitType` có được gọi không?

**Đáp:** Có. Class thường và record đều là `TypeElement`, nên dispatch đến `visitType`. Phân biệt qua `e.getKind()`; demo phát lỗi nếu kết quả không phải `RECORD`.

**Câu 4.** Muốn kiểm tra một method nhận tham số `List<String>` có hợp lệ để gán cho kiểu khác, nên dựa vào scanner hay `Types`?

**Đáp:** Scanner giúp tìm method/parameter; **`Types`** (cùng các `TypeMirror`/`DeclaredType` thích hợp) kiểm tra ngữ nghĩa kiểu. Hai công cụ giải quyết những việc khác nhau.

**Câu 5.** Muốn lấy inherited methods của một class, có thể chỉ gọi `scanner.scan(type)` rồi giả định đủ hết không?

**Đáp:** Không. Scanner đi qua các khai báo nằm bên trong theo hợp đồng của nó, không tự thêm mọi member kế thừa. Cần dùng `Elements.getAllMembers(type)` khi yêu cầu gồm inherited members.

**Câu 6.** `ElementScanner14<Void,Void>` đã chạy qua 10 node; kết quả trả về có tự động bằng 10 không?

**Đáp:** Không. `Void` không mang bộ đếm, và `scan` không tự tổng hợp. Tạo collector trong scanner hoặc truyền context riêng để đếm.

**Câu 7.** Nếu cần xử lý một `String[]` hoặc `List<? extends Number>` theo từng kiểu, nên dùng `visitRecordComponent` không?

**Đáp:** Không. Đó là kiểu (`TypeMirror`); chọn `TypeVisitor`/`TypeKindVisitor14` hoặc `Types`. `RecordComponentElement` là một khai báo cụ thể trong record.

**Câu 8.** Vì sao demo chạy được trên JDK 17+ dù dùng class tên `ElementScanner14`?

**Đáp:** `14` là thế hệ visitor hỗ trợ các cấu trúc ngôn ngữ tương ứng, gồm record; API này tiếp tục hiện diện trên các JDK hiện hành, và demo dùng `--release 17` để biên dịch.

**Tóm tắt:** Để xử lý mô hình khai báo Java đúng cách, dùng **`ElementVisitor`/`SimpleElementVisitor14` để phân loại một phần tử** và **`ElementScanner14` để duyệt đệ quy những phần tử chứa bên trong**. Kiểm soát `super.visitXyz(...)`, `ElementKind`, phạm vi root và nhiều round; dùng `Types` nếu bài toán là quan hệ kiểu, dùng `Messager` nếu cần báo lỗi. Đây là những API Java SE ổn định đang được dùng trong annotation processing hiện đại.

### Tài liệu chính thức

- [Java SE 26 — Element và `accept(...)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html)
- [Java SE 26 — ElementVisitor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/ElementVisitor.html)
- [Java SE 26 — SimpleElementVisitor14](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/SimpleElementVisitor14.html)
- [Java SE 26 — ElementScanner14](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementScanner14.html)
- [Java SE 26 — ElementKindVisitor14](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementKindVisitor14.html)
- [Java SE 26 — ElementFilter](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementFilter.html)
- [Java SE 26 — TypeVisitor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeVisitor.html)
- [Java SE 26 — RoundEnvironment](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
