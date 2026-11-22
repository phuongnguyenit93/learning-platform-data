# Tương thích annotation processor khi compiler bổ sung loại phần tử mới

## Mục tiêu học tập

Trong chủ đề **Mô hình khai báo** của Java, annotation processor làm việc với các đối tượng `Element` đại diện cho class, interface, method, field, package, module, record component và các loại khai báo khác. Khi Java phát triển, mô hình này cũng có thể xuất hiện **`ElementKind` mới hoặc phương thức visitor mới**.

Sau bài học, bạn có thể:

- Giải thích vì sao một annotation processor đang chạy tốt với một JDK có thể **ném lỗi hoặc bỏ sót phần tử** sau khi nâng compiler/source level.
- Phân biệt `Element`, `ElementKind`, `TypeElement`, `RecordComponentElement`, `ElementVisitor` và hai nhóm giải pháp duyệt cây: `SimpleElementVisitor14` và `ElementScanner14`.
- Viết visitor có chiến lược rõ ràng cho phần tử đã biết (`visitType`, `visitRecordComponent`), phần tử chưa xử lý cụ thể (`defaultAction`) và loại phần tử vượt khả năng nhận diện (`visitUnknown`).
- Hiểu các ví dụ lịch sử **vẫn có ý nghĩa hiện nay**: module (`MODULE`), record (`RECORD`), record component (`RECORD_COMPONENT`) và binding variable (`BINDING_VARIABLE`).
- Xây dựng phép kiểm thử tích hợp với `javac` cho cả class thông thường và record; xác minh số record components thực sự được duyệt, thay vì chỉ xem compiler có trả mã thành công.
- Định nghĩa chính sách **tương thích tiến về phía trước**: ghi diagnostics, xử lý không rõ một cách có chủ ý, kiểm thử trên các JDK được hỗ trợ và chỉ công bố source version đã được kiểm chứng.

**Điều kiện thực hành:** JDK 17+ với `javac`, không cần thư viện ngoài JDK. Ví dụ sử dụng API chuẩn của module `java.compiler`, đang được duy trì trong Java hiện đại. Những thay đổi của phiên bản cũ chỉ được dùng để làm rõ nguyên nhân tương thích; không khuyến nghị phụ thuộc cách kích hoạt annotation processing mặc định đã thay đổi từ JDK 23.

## 1. Tại sao thêm một loại phần tử lại ảnh hưởng processor cũ?

Một annotation processor có thể đọc source qua:

```java
Element element = ...;
ElementKind kind = element.getKind();
```

hoặc áp dụng visitor:

```java
String result = element.accept(visitor, null);
```

Hai đoạn trên là **minh họa bên trong processor**; biến `element` và `visitor` phải được cấp từ môi trường compile-time. Chúng không phải chương trình `main` độc lập.

Giả sử processor trước đây chỉ quan tâm `CLASS` và `FIELD`. Sau khi Java bổ sung `record`, một đầu vào:

```java
record Ticket(String id, int count) {}
```

có thể xuất hiện trong mô hình compiler với:

- `TypeElement` của `Ticket` có `ElementKind.RECORD` (không phải `CLASS`).
- Từng declaration `id` và `count` trong record header được biểu diễn bằng `RecordComponentElement` có `ElementKind.RECORD_COMPONENT`.
- Record còn có các thành phần được sinh ngầm, chẳng hạn accessor, field, constructor; **chúng không thay thế hoàn toàn record component như một phần tử khai báo riêng**.

Nếu processor dùng:

```java
if (element.getKind() == ElementKind.CLASS) {
    // kiểm tra mọi class cần quan tâm
}
```

thì `Ticket` không đi qua nhánh này. Build vẫn có thể **hoàn tất thành công** nhưng quy tắc kiểm tra đã bỏ sót record — nguy hiểm hơn lỗi ném exception vì rất dễ bị bỏ qua trong CI.

Nếu visitor chưa có cách xử lý `RecordComponentElement`, lời gọi `accept(...)` có thể điều hướng đến `visitUnknown(...)`. Triển khai mặc định ở họ `AbstractElementVisitor6` có thể ném `UnknownElementException`. Đây là dạng **lỗi rõ ràng** khi cấu trúc ngôn ngữ mới đi vào processor.

Một processor tương thích tốt phải giải quyết **cả hai tình huống**:

1. **Không crash ngoài ý muốn** khi nhận loại phần tử mới.
2. **Không im lặng xem là đã kiểm tra hợp lệ** đối với loại phần tử nằm ngoài phạm vi kiểm chứng của nó.

## 2. Những khái niệm trong mô hình khai báo

| API | Vai trò |
| --- | --- |
| `Element` | Giao diện mô tả một phần tử chương trình ở **compile time**: module, package, type, field, method, record component... |
| `Element.getKind()` | Trả về một giá trị `ElementKind` mô tả loại phần tử. |
| `TypeElement` | Mô hình class, interface, enum, record, annotation interface ở mức khai báo. |
| `RecordComponentElement` | Mô hình một thành phần khai báo trong record header. |
| `ElementVisitor<R,P>` | Hợp đồng visitor; `R` là kiểu trả về, `P` là kiểu tham số đi kèm. |
| `SimpleElementVisitor14<R,P>` | Visitor có `defaultAction` hữu ích khi chỉ muốn xử lý vài loại element nhất định. |
| `ElementScanner14<R,P>` | Visitor chủ động **duyệt các phần tử con**, dùng khi cần quét cây khai báo. |
| `ElementKindVisitor14<R,P>` | Visitor dispatch chi tiết theo `ElementKind`, ví dụ record/enum/class, khi cần phân biệt kind. |
| `RoundEnvironment` | Cho processor các phần tử được gắn annotation trong một round. |
| `ProcessingEnvironment` | Cung cấp `Elements`, `Types`, `Messager`, `Filer` và source version đang biên dịch. |

Một `TypeElement` có thể có kind là `CLASS`, `ENUM`, `INTERFACE`, `ANNOTATION_TYPE` hoặc `RECORD`. Vì vậy, **kiểu Java của object (`TypeElement`) và giá trị `ElementKind` của nó không đồng nhất**.

Không nên chỉ dựa vào `element instanceof SomeElementInterface` để suy ra loại *ngữ nghĩa* của element: Javadoc của `Element` lưu ý một implementation có thể dùng cùng object cho nhiều subinterfaces. Ưu tiên visitor hoặc `getKind()` để phân loại.

## 3. Ví dụ về các lần mở rộng đã xảy ra trong Java

Đây đều là **khái niệm đang tồn tại** trong Java hiện đại, không phải đề xuất cho tương lai:

| ElementKind | Vai trò hiện nay | Bối cảnh phiên bản |
| --- | --- | --- |
| `MODULE` | Mô tả module của Java Platform Module System. | Từ Java 9 |
| `RECORD` | Record class; là loại type riêng, không có kind `CLASS`. | Từ Java 16 khi record trở thành tính năng chính thức |
| `RECORD_COMPONENT` | Một component trong record header. | Từ Java 16 |
| `BINDING_VARIABLE` | Biến ràng buộc của pattern. | Từ Java 16 |
| `CLASS`, `INTERFACE`, `ENUM` | Các loại khai báo type cơ bản. | Vẫn được sử dụng |
| `FIELD`, `METHOD`, `PARAMETER` | Các phần tử field, method, parameter. | Vẫn được sử dụng |

**Phân biệt:** `RECORD_COMPONENT` không phải `FIELD`; một record component có thể dẫn đến các thành phần sinh ra tương ứng nhưng vẫn giữ danh tính riêng trong model. Khi lập quy tắc validate, không nên kiểm tra mọi thứ bằng `ElementFilter.fieldsIn(...)` rồi nghĩ đã duyệt các record components.

Với `ElementKind`, Javadoc còn cảnh báo **có thể bổ sung các enum constants khác trong những bản Java sau** để đại diện cho cấu trúc ngôn ngữ chưa biết. Vì vậy processor không nên giả định danh sách kind là một tập bất biến vĩnh viễn.

### `ElementKind` có các helper hiện hành, nhưng chú ý baseline

Trên JDK mới hơn, `ElementKind` có các helper như `isClass()`, `isInterface()`, `isField()`, `isVariable()`. Ví dụ:

```java
boolean classLike = kind.isClass();
```

`isClass()` bao gồm `CLASS`, `ENUM` và `RECORD`. Tuy nhiên, một số helper phân loại dạng tổng quát này được bổ sung **từ Java 19**; nếu dự án phải **biên dịch processor trên JDK 17**, không đưa chúng vào ví dụ chính. Hãy dùng các kinds đã tồn tại trên Java 17 hoặc điều chỉnh baseline toolchain có chủ đích.

Một API tiện hơn trong JDK mới không có nghĩa mọi bản JDK được dự án hỗ trợ đều cung cấp nó.

## 4. Hai trục tương thích phải được kiểm soát

**Trục 1 — Compiler/runtime dùng để chạy processor.** Ví dụ javac từ JDK 24 tải một JAR processor được biên dịch cho Java 17. JVM chạy compiler phải đọc được class file của processor và API mà nó dùng.

**Trục 2 — Source language level của mã ứng dụng.** Lựa chọn `--release 17` quy định compiler phân tích Java 17, dù JDK host có thể mới hơn. Trong processor:

```java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
```

khai báo phiên bản source cao nhất mà processor **tuyên bố hỗ trợ**. Nó không bảo đảm processor tự xử lý đúng mọi loại element mới ở bản Java 21, 24 hoặc tương lai.

| Câu hỏi | Kiểm tra |
| --- | --- |
| JDK hiện tại có tải và chạy processor được không? | Thực thi build processor trên JDK thực tế. |
| Processor có hỗ trợ source level đích không? | `getSupportedSourceVersion()` cùng các integration tests. |
| Source đang biên dịch với level nào? | `processingEnv.getSourceVersion()` và lựa chọn compiler `--release`/`-source`. |
| Processor có nhận các kinds mới không? | Source fixtures chứa cấu trúc mới và assertions cho đường đi xử lý. |
| Có missing diagnostics hoặc bỏ sót công việc? | Kiểm chứng đầu ra semantic, không chỉ exit code. |

Với processor đa JDK, phải chạy các phép thử trên **những toolchain được tổ chức công bố hỗ trợ**, không coi một lần build xanh trên JDK 17 là bằng chứng đủ cho mọi bản sau.

## 5. `ElementVisitor`, `defaultAction` và `visitUnknown`

### 5.1. `accept` dispatch theo loại element

`Element.accept(ElementVisitor<R,P> visitor, P parameter)` gọi đúng phương thức visitor tương ứng với element. Với một `RecordComponentElement` đã được model nhận biết, visitor hiện đại gọi `visitRecordComponent(...)`; với `TypeElement` record, visitor nhận phương thức `visitType(...)` và có thể quan sát `e.getKind() == RECORD`.

```java
// Trong code đã có Element e và visitor nhận String, Void:
String description = e.accept(visitor, null);
```

**Chi tiết dễ nhầm:** `Element.accept` có **hai tham số** (visitor và tham số phụ). Nó không có overload `accept(visitor)` trong giao diện này. Một số lớp visitor có tiện ích `visitor.visit(e)` với một tham số; hai cách có thể tương đương, nhưng khi gọi trực tiếp `accept` phải truyền `null` nếu tham số loại `Void` không dùng.

### 5.2. `defaultAction` dành cho loại element *đã biết* nhưng chưa xử lý riêng

Với `SimpleElementVisitor14`, bạn có thể override:

```java
@Override
protected String defaultAction(Element e, Void unused) {
    return "other:" + e.getKind();
}
```

Đây là hành vi dự phòng cho những phương thức visitor mặc định gọi `defaultAction` (ví dụ `visitVariable` khi bạn không override). Nếu processor chỉ muốn đánh nhãn field đã biết mà không có chính sách xử lý đặc biệt, đây là lựa chọn gọn.

**Không nên kết luận `defaultAction` sẽ luôn bắt mọi loại element tương lai.** Khi giao diện `ElementVisitor` bổ sung một method mới, implementation mặc định có thể chuyển qua `visitUnknown`, không tự nhiên chuyển tới `defaultAction` của subclass.

### 5.3. `visitUnknown` dành cho element không có nhánh visitor phù hợp

Javadoc mô tả `visitUnknown(Element e,P p)` cho trường hợp Java phát triển và hierarchy có loại element chưa biết với visitor đang sử dụng.

Ví dụ chính sách “tiếp tục để báo cáo”:

```java
@Override
public String visitUnknown(Element e, Void unused) {
    return "unknown:" + e.getKind();
}
```

Đây là **đoạn cài đặt trong visitor**, chưa phải một chương trình độc lập.

Nếu processor chỉ là công cụ thống kê/tài liệu hóa, ghi cảnh báo và tiếp tục một cách có kiểm soát có thể hợp lý. Nếu processor là **bộ kiểm tra đảm bảo quy tắc an toàn hoặc sinh mã có yêu cầu đầy đủ**, nuốt phần tử không biết rồi báo mọi thứ hợp lệ lại là sai.

Chính sách nghiêm hơn:

```java
@Override
public String visitUnknown(Element e, Void unused) {
    throw new IllegalStateException(
            "Unsupported element kind: " + e.getKind());
}
```

Trong production, có thể dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., e)` để báo lỗi gắn với phần tử thay vì dừng bằng exception khó đọc.

**Điều quan trọng:** một nhánh dự phòng phải có **chủ ý nghiệp vụ**, không chỉ để ứng dụng không crash.

### 5.4. Vì sao có `UnknownElementException`?

Họ `AbstractElementVisitor6` định nghĩa implementation mặc định của `visitUnknown(...)` ném `UnknownElementException`. Đây là cơ chế phát hiện rằng visitor chưa cam kết hỗ trợ loại element ấy. Nếu processor sử dụng visitor thuộc thế hệ chưa xử lý record component, một record component có thể đi vào đường này và gây lỗi trong quá trình build.

Từ quan điểm tương thích, không nên dùng `catch (Exception ignored)` quanh toàn bộ processor để “chữa” vấn đề. Nó chỉ che lỗi và cho ra kết quả thiếu dữ liệu. Hãy nâng visitor phù hợp baseline, override `visitUnknown` theo chính sách thực sự và kiểm thử loại element mới.

## 6. Chọn họ visitor nào?

| Họ visitor | Khi nào dùng | Hành vi đáng quan tâm |
| --- | --- | --- |
| `SimpleElementVisitor14` | Muốn xử lý một số kinds và có `defaultAction` cho những element đã biết. | Có `visitRecordComponent`; có thể override `visitUnknown` cho unknown. |
| `ElementScanner14` | Muốn duyệt **cây phần tử**, bao gồm type parameters, members và record components. | `scan(e)` đệ quy qua các thành phần theo API; override method rồi gọi `super` nếu muốn tiếp tục traversal. |
| `ElementKindVisitor14` | Cần phân biệt `CLASS`, `ENUM`, `RECORD`, loại variable cụ thể và ghi logic theo kind. | Có những `visitXyzAsKind`; thêm kinds có thể cần xử lý bổ sung. |
| `AbstractElementVisitor14` | Muốn buộc subclass tự triển khai các phương thức cần thiết, không cần fallback `defaultAction` kiểu simple visitor. | Phù hợp khi cố ý yêu cầu logic tường minh; cần hiểu `visitUnknown`. |

Những con số trong tên lớp visitor là **thế hệ cấu trúc ngôn ngữ** mà class visitor được thiết kế để hỗ trợ, không phải lệnh buộc source target luôn đúng bằng số đó. Ví dụ `SimpleElementVisitor14` vẫn là API hợp lệ trong Java SE 26 và dùng được trên JDK 17+.

Bài thực hành dùng **`SimpleElementVisitor14` và `ElementScanner14`** để có cả hai loại hành vi: thăm một element theo yêu cầu và quét các elements con.

Không chọn lớp có chữ `Preview` làm mặc định trong thư viện production nếu không chủ động quản lý preview features. Ưu tiên API chuẩn, không preview khi bài toán không cần tính năng thử nghiệm.

### Vấn đề tên các method bắt đầu bằng `visit`

Javadoc của các lớp visitor cảnh báo rằng trong tương lai có thể **bổ sung phương thức `visit...`**. Do đó, subclass **không nên tự nghĩ thêm các instance methods có tên bắt đầu bằng `visit`** không nằm trong contract hiện tại, vì có thể vô tình trùng tên một phương thức sẽ được API thêm ở phiên bản sau.

Khi muốn override method đã có, dùng `@Override` để compiler kiểm tra chữ ký. Với helper riêng, chọn tên như `describeRecord(...)`, `handleField(...)`, `validateElement(...)` thay vì `visitFutureThing(...)`.

## 7. Ví dụ chạy được Java 17+: processor xử lý class và record

Ví dụ tạo annotation `@Audit`, một class thông thường, một record, và processor dùng **hai kiểu visitor**:

- `SimpleElementVisitor14` phân loại `CLASS`, `RECORD`, `FIELD` và mô tả hai `RECORD_COMPONENT`.
- `ElementScanner14` đếm record components thực sự được duyệt trong các phần tử con.
- `visitUnknown` được triển khai sẵn như một nhánh bảo vệ cho element chưa hỗ trợ. Trong **JDK 24 với source fixture này**, không có element tương lai nên nhánh `visitUnknown` **không được kích hoạt**; đây là điều bình thường và được nói rõ để tránh hiểu nhầm là đã kiểm thử được một cấu trúc Java chưa tồn tại.

### 7.1. Cấu trúc file

```text
compat-demo/
├── processor/
│   └── compat/
│       └── processor/
│           └── CompatibilityProcessor.java
├── src/
│   └── compat/
│       ├── Audit.java
│       ├── Box.java
│       └── Ticket.java
└── out/
    ├── processor/  (được tạo khi build)
    └── classes/    (được tạo khi build)
```

### 7.2. Annotation `src/compat/Audit.java`

```java
package compat;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Audit {}
```

`@Target(TYPE)` cho phép gắn `@Audit` lên class/record. `RetentionPolicy.SOURCE` đủ cho compiler xử lý annotation ở thời gian biên dịch; không cần lưu lại annotation này trong bytecode.

### 7.3. Class truyền thống: `src/compat/Box.java`

```java
package compat;

@Audit
class Box {
    String label;
}
```

`Box` được biểu diễn bởi `TypeElement` có kind `CLASS`. Field `label` có kind `FIELD`. Chúng sẽ đi qua `visitType` và `defaultAction` tương ứng.

### 7.4. Record: `src/compat/Ticket.java`

```java
package compat;

@Audit
record Ticket(String id, int count) {}
```

`Ticket` là một `TypeElement` với `getKind() == RECORD`; `id` và `count` là `RecordComponentElement` trong record header. Vì record đã là tính năng chính thức từ Java 16, fixture này hợp lệ với Java 17 mà không cần `--enable-preview`.

### 7.5. Processor đầy đủ: `processor/compat/processor/CompatibilityProcessor.java`

```java
package compat.processor;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.RecordComponentElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.ElementFilter;
import javax.lang.model.util.ElementScanner14;
import javax.lang.model.util.SimpleElementVisitor14;

@SupportedAnnotationTypes("compat.Audit")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class CompatibilityProcessor extends AbstractProcessor {
    private boolean checked;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (checked || round.processingOver()) return true;

        TypeElement marker = processingEnv.getElementUtils()
                .getTypeElement("compat.Audit");
        List<Element> items = new ArrayList<>(round.getElementsAnnotatedWith(marker));
        items.sort(Comparator.comparing(e -> e.getSimpleName().toString()));

        var visitor = new SimpleElementVisitor14<String, Void>() {
            @Override
            public String visitType(TypeElement e, Void unused) {
                return "type:" + e.getKind();
            }

            @Override
            public String visitRecordComponent(RecordComponentElement e, Void unused) {
                return "record-component:" + e.getSimpleName() + ":" + e.asType();
            }

            @Override
            protected String defaultAction(Element e, Void unused) {
                return "other:" + e.getKind();
            }

            @Override
            public String visitUnknown(Element e, Void unused) {
                return "unknown:" + e.getKind();
            }
        };

        for (Element item : items) {
            System.out.println("item=" + item.getSimpleName()
                    + ",kind=" + item.getKind()
                    + ",visitor=" + item.accept(visitor, null));

            if (item.getKind() == ElementKind.RECORD) {
                TypeElement record = (TypeElement) item;
                System.out.println("components=" + record.getRecordComponents().size());
                for (RecordComponentElement component : record.getRecordComponents()) {
                    System.out.println("visit=" + component.accept(visitor, null));
                }
            } else if (item.getKind() == ElementKind.CLASS) {
                for (VariableElement field : ElementFilter.fieldsIn(item.getEnclosedElements())) {
                    System.out.println("visit=" + field.accept(visitor, null));
                }
            }

            final int[] count = {0};
            new ElementScanner14<Void, Void>() {
                @Override
                public Void visitRecordComponent(RecordComponentElement e, Void unused) {
                    count[0]++;
                    return super.visitRecordComponent(e, unused);
                }
            }.scan(item);

            System.out.println("scanned-components=" + count[0]);
        }
        checked = true;
        return true;
    }
}
```

### 7.6. Build bằng PowerShell trên Windows

Tại thư mục `compat-demo`:

```powershell
New-Item -ItemType Directory -Force out\processor, out\classes | Out-Null

javac --release 17 -d out\processor processor\compat\processor\CompatibilityProcessor.java

javac --release 17 -processorpath out\processor -processor compat.processor.CompatibilityProcessor -proc:only -d out\classes src\compat\Audit.java src\compat\Box.java src\compat\Ticket.java
```

### 7.7. Build bằng Bash trên Linux/macOS

```bash
mkdir -p out/processor out/classes

javac --release 17 -d out/processor \
  processor/compat/processor/CompatibilityProcessor.java

javac --release 17 \
  -processorpath out/processor \
  -processor compat.processor.CompatibilityProcessor \
  -proc:only \
  -d out/classes \
  src/compat/Audit.java src/compat/Box.java src/compat/Ticket.java
```

`-processorpath` và `-processor` chọn processor **tường minh**; đây là cách ổn định trên JDK mới, đặc biệt vì JDK 23 đã thay đổi mặc định tìm và chạy annotation processors. `-proc:only` chạy annotation processing nhưng không sinh `Box.class` hay `Ticket.class` từ các source fixture; nhiệm vụ của bài là kiểm tra model và visitor, không phải chạy bytecode ứng dụng.

### 7.8. Kết quả chính xác đã kiểm tra với JDK 24

```text
item=Box,kind=CLASS,visitor=type:CLASS
visit=other:FIELD
scanned-components=0
item=Ticket,kind=RECORD,visitor=type:RECORD
components=2
visit=record-component:id:java.lang.String
visit=record-component:count:int
scanned-components=2
```

Tại sao output ổn định?

- `items.sort(...)` sắp theo tên đơn giản của `Box` và `Ticket`, thay vì giả định thứ tự của `Set` từ `RoundEnvironment`.
- `Box` có một field `label`; `visitVariable` đi theo `defaultAction` và trả `other:FIELD`.
- `Ticket` có đúng hai record components `id` và `count`; `getRecordComponents()` trả theo thứ tự khai báo trong record header.
- `ElementScanner14` tự quét các thành phần con và gọi `visitRecordComponent` hai lần đối với `Ticket`, không lần nào đối với `Box`.
- Lệnh `javac` thành công chứng tỏ processor và fixture hợp lệ; **các dòng output chứng minh đã xử lý đúng các loại phần tử quan trọng**, chứ không chỉ là kết quả build xanh chung chung.

**Chú ý:** ví dụ kiểm tra thủ công output để học cách hoạt động. Trong CI chuyên nghiệp nên có assertions hoặc expected-result checks thực sự, không chỉ in log.

## 8. Phân tích từng lựa chọn trong processor

### 8.1. Vì sao kiểm tra `ElementKind.RECORD` trước khi gọi `getRecordComponents()`?

`getRecordComponents()` là API của `TypeElement`, nhưng danh sách chỉ có ý nghĩa với type được khai báo là record. Nhánh `if (item.getKind() == ElementKind.RECORD)` xác định chính xác đây là record class, sau đó ép về `TypeElement` và đọc header components.

Không nhầm `RECORD_COMPONENT` với `FIELD`; record component có thể liên quan đến field/accessor tổng hợp, nhưng các entity đó là những phần tử khác trong model. Cần hiểu bài toán đang kiểm tra record header hay field thực tế.

### 8.2. Vì sao dùng `SimpleElementVisitor14` thay vì một chuỗi `if (kind == ...)`?

Visitor khiến quy tắc xử lý phân tách theo **loại mô hình** và tự dispatch từ `Element.accept(...)`. Nó giúp phân biệt:

- `visitType` cho class/record/enum/interface dưới dạng `TypeElement`;
- `visitRecordComponent` cho record component;
- `defaultAction` cho loại đã biết chưa có handler riêng, ví dụ `FIELD` trong demo;
- `visitUnknown` cho nhánh tương thích với loại element không có handler nhận biết.

Một chuỗi `if` hoặc `switch` không sai, nhưng bạn phải tự duy trì mọi nhánh. Đối với processor mở rộng theo JDK, visitor thường trình bày contract rõ hơn và giúp thiết kế chính sách cho unknown elements.

### 8.3. Vì sao vẫn cần `ElementScanner14`?

Visitor thường chỉ thăm **một element** được truyền cho nó. Để đi qua các phần tử con, bạn phải chủ động duyệt hoặc dùng scanner. `ElementScanner14` quét type parameters/enclosed elements/parameters theo contract của từng method.

Trong demo, scanner không dựa vào việc biết record chứa mấy field/accessor sinh ngầm; nó chỉ đếm **lượt ghé thăm `RecordComponentElement`**.

Nếu override một method scanner mà vẫn muốn duyệt các phần tử con, nên gọi `super.visitXyz(e, p)`. Nếu bỏ lời gọi `super` một cách vô ý, thuật toán quét có thể dừng ở một node mà không báo lỗi, gây thiếu dữ liệu.

### 8.4. Đừng nghĩ `visitUnknown` đã được chạy vì trong code có override

Fixture chỉ chứa các loại đã biết với Java 17+ (`CLASS`, `FIELD`, `RECORD`, `RECORD_COMPONENT`). Output **không có dòng `unknown:...`**. Điều này không làm đoạn override vô ích: nó định nghĩa chính sách khi một loại mới xuất hiện trong tương lai.

Một integration test cho **thật sự loại mới** chỉ có thể được chạy khi có compiler/JDK cung cấp loại đó. Không thể tự khẳng định tính tương thích với một cấu trúc chưa tồn tại bằng cách chỉ gọi thử `visitUnknown` thủ công.

## 9. Làm thế nào để tránh “tương thích giả” do nhánh mặc định?

Một processor chạy không crash nhưng bỏ qua quy tắc nghiệp vụ vẫn có thể gây lỗi.

Ví dụ giả định: bộ kiểm tra bắt mọi khai báo DTO phải có annotation `@Validated`. Nếu nó chỉ tìm `ElementKind.CLASS`, sau khi dự án thêm:

```java
record RequestDto(String name) {}
```

thì `RequestDto` có thể không được kiểm tra, dù build thành công. **Không có exception** nhưng validation bị bỏ qua.

Một cách thiết kế rõ ràng là tách yêu cầu thành hai phần:

1. **Phạm vi type hợp lệ:** class thông thường, record, enum...? Quyết định theo nghiệp vụ. Một số validation áp dụng cho mọi declaration type, một số chỉ dành cho class.
2. **Phạm vi code hiện hỗ trợ:** processor đã triển khai xử lý tất cả các loại đó chưa? Nếu chưa, phải phát diagnostic hoặc từ chối cấu trúc không hỗ trợ.

Ví dụ helper minh họa cho Java 17+:

```java
static boolean supportsDtoKind(ElementKind kind) {
    return kind == ElementKind.CLASS
            || kind == ElementKind.RECORD;
}
```

Đây là một **đoạn helper**, không phải toàn bộ processor. Nếu quy tắc thật sự cho phép record, code nên chủ động hỗ trợ nó chứ không để `defaultAction` bỏ qua.

Trên JDK 19+ có các helper `ElementKind.isClass()` thuận tiện, nhưng API đó không thuộc baseline Java 17 của ví dụ; hãy chọn theo phiên bản processor phải biên dịch.

### Đừng dùng `defaultAction` để tuyên bố mọi thứ hợp lệ

Một visitor dùng:

```java
@Override
protected Boolean defaultAction(Element e, Void unused) {
    return true;
}
```

có thể rất nguy hiểm trong validator nếu `true` mang nghĩa "đã kiểm tra và đạt". Nó sẽ gộp "không thuộc loại quan tâm" và "đã được kiểm tra" thành một trạng thái.

Thiết kế tốt hơn là một kết quả phân loại riêng như `HANDLED`, `NOT_APPLICABLE`, `UNSUPPORTED` hoặc một object chứa diagnostics. Khi phải validate các loại mới, chuyển `UNSUPPORTED` thành cảnh báo hoặc lỗi thay vì coi là pass.

## 10. Chiến lược cho `switch(ElementKind)` khi enum được mở rộng

Javadoc ghi rõ `ElementKind` có thể được bổ sung hằng enum. Vì vậy code dạng:

```java
switch (element.getKind()) {
    case CLASS:
        validateClass(element);
        break;
    case RECORD:
        validateRecord(element);
        break;
    default:
        reportUnsupported(element);
}
```

là một **mô hình minh họa**, với các helper `validateClass`, `validateRecord`, `reportUnsupported` thuộc về ứng dụng; đoạn này **không tự chạy độc lập**. Vai trò của `default` là tránh giả định mọi kind hiện tại và tương lai đều đã có case tường minh.

Nếu dùng switch expression Java 17+, có thể mô tả trạng thái rõ ràng:

```java
static String classify(ElementKind kind) {
    return switch (kind) {
        case CLASS -> "ordinary-class";
        case RECORD -> "record";
        case ENUM -> "enum";
        default -> "unsupported:" + kind;
    };
}
```

Khi `ElementKind` được thêm constant trong tương lai, nhánh `default` cho kết quả có chủ đích. Tuy nhiên, nếu ứng dụng coi `unsupported` như thành công thì vẫn bị bỏ sót nghiệp vụ; phải quyết định cách ứng xử với trạng thái đó.

**Lưu ý:** ngay cả khi code enum-switch chạy được trên JDK mới, việc xử lý **đúng ngữ nghĩa** của kind mới vẫn cần được implement và test. Tương thích nhị phân hoặc tránh crash không đồng nghĩa tương thích về chức năng.

## 11. Cần kiểm thử gì khi nâng compiler?

Không chỉ thử `javac -version` và biên dịch processor. Hãy chạy một ma trận test ứng với những source levels và tính năng Java có liên quan:

| Ca | Fixture | Điều cần kiểm chứng |
| --- | --- | --- |
| Class thường | `class Box { String label; }` | Processor nhận `CLASS`, duyệt đúng field. |
| Enum | `enum State { READY, DONE }` | Nếu phạm vi áp dụng có enum, không chỉ kiểm tra `CLASS`. |
| Annotation interface | `@interface Marker {}` | Nếu công cụ xử lý khai báo annotation, xác định `ANNOTATION_TYPE`. |
| Module | `module example.module { ... }` | Nếu processor hỗ trợ module-aware compilation, không bỏ qua `MODULE`. |
| Record | `record Ticket(String id, int count) {}` | Processor nhận `RECORD` và kiểm tra đúng record header. |
| Record component | `id`, `count` | Visitor/scanner phải ghé thăm đúng `RecordComponentElement`. |
| Binding variable | Pattern binding trong source được hỗ trợ | Nếu công cụ thực sự phân tích variables qua compiler model, xử lý đúng `BINDING_VARIABLE` khi xuất hiện. |
| New kind ở JDK tương lai | Fixture dùng cú pháp nguồn mới, khi đã có | Chính sách `visitUnknown`/unsupported đúng; không crash hoặc im lặng pass. |
| Multiple processing rounds | Processor tạo source mới và round tiếp theo | Không đếm trùng hoặc bỏ qua elements, không giữ state sai. |
| Source level mới | `--release <supported>` được hỗ trợ | Supported source version đã kiểm tra, không bỏ qua cảnh báo tương thích. |

Các ca test cần **cả positive và negative assertions**. Ví dụ với một record có hai components, hãy kiểm tra đúng **hai lần ghé thăm record components**, không chỉ xem code javac không ném exception.

Có thể kiểm thử ở hai mức:

- **Unit test** cho các helper phân loại `ElementKind`, chính sách `HANDLED/UNSUPPORTED`, mã chuẩn hóa diagnostics.
- **Integration test** thực sự khởi chạy javac với processor path, source fixtures và assertion trên kết quả/diagnostics/outputs; đây là cách bắt vấn đề dispatcher/visitor và compiler model thực tế.

Cần kiểm thử trên JDK mà ứng dụng hỗ trợ và các source levels mà processor **công bố** hỗ trợ. Một phần tử mới có thể xuất hiện trên compiler mới nhưng không xuất hiện khi dùng `--release` cũ; hai chiều JDK host/source target phải được ghi rõ.

## 12. `@SupportedSourceVersion` và lời cảnh báo khi nâng JDK

Trong ví dụ:

```java
@SupportedSourceVersion(SourceVersion.RELEASE_17)
```

processor khai báo hỗ trợ source Java 17. Nếu javac mới được dùng để biên dịch source version mới hơn, nó có thể phát cảnh báo rằng source version mà processor hỗ trợ thấp hơn source version hiện tại.

Không khắc phục bằng cách chỉ đổi annotation thành version mới mà không test. Cập nhật cần dựa vào **mã nguồn fixture và các logic xử lý element mới** đã được kiểm chứng.

Một lựa chọn khác của API là:

```java
@Override
public SourceVersion getSupportedSourceVersion() {
    return SourceVersion.latestSupported();
}
```

Đây là **đoạn tùy biến**, không phải một chương trình hoàn chỉnh. Nó khai báo version mới nhất mà execution environment hiện tại hỗ trợ đầy đủ; **không** có nghĩa processor của bạn tự nhiên hiểu mọi loại `ElementKind` hay cú pháp Java mới. Chỉ dùng khi chính sách tương thích của processor thực sự cho phép và có test xác nhận.

Đối với thư viện compiler tools muốn phát hành lâu dài, một quy trình an toàn hơn:

1. Ghi rõ minimum JDK để chạy processor và những source versions được hỗ trợ.
2. Có test fixtures cho constructs mà source level mới đem lại.
3. Chạy bộ test trên JDK mới trước khi công bố version tương ứng.
4. Nếu bộ phân tích chưa hỗ trợ một kind mới quan trọng, phát cảnh báo/lỗi có thể xử lý thay vì đánh dấu pass.
5. Cập nhật metadata hỗ trợ sau khi đã sửa và test.

**Chú ý thêm:** Trên JDK 23+, annotation processing cần cấu hình kích hoạt thích hợp, chẳng hạn chỉ định `-processor` tường minh như ví dụ. Nếu không bật processor, CI có thể **xanh giả** vì compiler chỉ biên dịch source và không hề chạy validator của bạn. Luôn có phép kiểm chứng rằng processor đã thực sự hoạt động.

## 13. Mô hình khai báo khác với AST đầy đủ

`javax.lang.model.element` biểu diễn **khai báo** trong mô hình biên dịch; không phải một API chuẩn bao phủ mọi cấu trúc statement/expression như `if`, `switch`, lambda body hoặc pattern expression.

Vì vậy:

- `ElementKind.BINDING_VARIABLE` biểu diễn một loại biến có thể được model cung cấp, nhưng không suy ra mỗi expression/pattern trong chương trình đều xuất hiện như phần tử con của `TypeElement.getEnclosedElements()`.
- Khi nhiệm vụ là phân tích *cú pháp/AST* chi tiết, có thể cần compiler tree API `com.sun.source.tree` và `com.sun.source.util` thuộc `jdk.compiler`, với hợp đồng riêng và điều kiện đóng gói tương ứng.
- Không “sửa” việc thiếu một `Element` bằng cách ép scanner đi qua các statement mà element model không cam kết mô tả.

Bài này tập trung vào **tính tương thích của processor dùng mô hình khai báo chuẩn**; chuyển sang AST analysis là một vấn đề khác cần thiết kế độc lập.

## 14. Xử lý unknown elements cho hai loại sản phẩm

### Công cụ thống kê/tài liệu hóa: tiếp tục có cảnh báo

Một công cụ chỉ báo cáo số loại declaration có thể ghi:

```java
@Override
public String visitUnknown(Element e, Void p) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.WARNING,
            "Skipped unsupported element kind: " + e.getKind(), e);
    return "unsupported:" + e.getKind();
}
```

Đây là **đoạn thêm vào processor**, cần import `javax.tools.Diagnostic`. Nó không tự làm compiler hiểu element mới; nó chỉ ghi nhận và tránh bỏ qua một cách âm thầm.

### Bộ sinh mã/validator có ràng buộc chặt: từ chối thiếu hỗ trợ

Nếu một processor cần đảm bảo mọi DTO đều được kiểm tra, có thể dùng:

```java
@Override
public String visitUnknown(Element e, Void p) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Cannot validate unsupported element kind: " + e.getKind(), e);
    return "unsupported:" + e.getKind();
}
```

Trong Java annotation processing, phát `Diagnostic.Kind.ERROR` làm compilation thất bại theo quy trình compiler. Nó giúp đội phát triển biết phải cập nhật processor khi thêm một language construct chưa được hỗ trợ.

Không nên dùng một policy duy nhất cho mọi library; lựa chọn tùy hậu quả của việc thiếu một element. **Điều bắt buộc là công bố policy và kiểm thử nó.**

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| Processor ném `UnknownElementException` | Visitor chưa xử lý kind mới, `visitUnknown` mặc định ném. | Dùng visitor phù hợp baseline và implement chiến lược unknown có chủ đích. |
| Record không bị validate dù build xanh | Code chỉ nhận `ElementKind.CLASS`. | Bổ sung `RECORD` khi nghiệp vụ áp dụng cho record. |
| Đếm record header bằng `fieldsIn(...)` cho kết quả không đúng kỳ vọng | Field và record component là những phần tử model khác. | Dùng `TypeElement.getRecordComponents()`, `RecordComponentElement` hoặc scanner phù hợp. |
| Scanner thiếu record components | Sử dụng visitor/scanner thế hệ không hỗ trợ hoặc override không gọi `super` khi cần. | Dùng `ElementScanner14` với traversal đúng; assert số node đã duyệt. |
| Một `switch` phân loại element bỏ sót kind mới | Giả định các enum constants không thay đổi. | Cung cấp `default` báo unsupported, sau đó bổ sung nhánh thật khi cần. |
| `defaultAction` làm validator pass tất cả | Gộp “không kiểm tra” với “đã kiểm tra”. | Dùng trạng thái `HANDLED` / `UNSUPPORTED` rõ ràng hoặc diagnostic. |
| Lệnh `accept(visitor)` báo lỗi biên dịch | `Element.accept` yêu cầu cả tham số phụ `P`. | Dùng `element.accept(visitor, null)` khi `P=Void` hoặc `visitor.visit(element)`. |
| Bị lỗi trên JDK 17 khi gọi helper ElementKind mới | Chọn API chỉ có từ Java 19+. | Giữ baseline đúng; dùng `ElementKind.RECORD`/`CLASS` cho ví dụ Java 17. |
| Compiler mới cảnh báo supported source version cũ | `@SupportedSourceVersion` nhỏ hơn source đang biên dịch. | Test với source level mới, rồi cập nhật chính sách/metadata khi đạt. |
| Processor không được chạy trên JDK 23+ | Build chưa kích hoạt annotation processing tường minh. | Cấu hình processor path và tên processor; kiểm tra output/diagnostic xác nhận chạy. |
| Tưởng đã kiểm thử tương lai vì có `visitUnknown` | Fixture hiện tại không chứa kinds chưa tồn tại. | Kiểm thử những kind hiện có, thử trên JDK mới khi xuất hiện, báo rõ chưa kiểm chứng tương lai. |
| So sánh class của object `Element` bằng `instanceof` để quyết định mọi loại | Implementation có thể triển khai nhiều element subinterfaces. | Ưu tiên `getKind()`/visitor theo model. |

## 16. Checklist review processor trước khi nâng Java

1. **Tài liệu hỗ trợ:** xác định baseline JDK của processor và source levels được công bố.
2. **API còn hiệu lực:** dùng `javax.lang.model`, `SimpleElementVisitor14`, `ElementScanner14` và `ElementKind` theo Javadoc hiện hành.
3. **Phạm vi kiểm tra:** xác định `CLASS`, `ENUM`, `RECORD`, `ANNOTATION_TYPE`, `MODULE`, `RECORD_COMPONENT` có liên quan tới nghiệp vụ không.
4. **Fallback rõ nghĩa:** `defaultAction` cho known-but-unhandled; `visitUnknown` cho unknown; không mặc định thiếu hỗ trợ là hợp lệ.
5. **Tránh xung đột tên method:** không tự đặt helper instance bắt đầu bằng `visit` trong subclass visitor; dùng `@Override` khi thực sự override API.
6. **Traversal:** kiểm tra `ElementScanner14` có đi qua node cần quan tâm, giữ `super.visitXyz` khi muốn scan tiếp.
7. **Kiểm thử ít nhất một record:** type kind `RECORD` và đúng số `RECORD_COMPONENT`, không chỉ class thường.
8. **Diagnostics:** khi unsupported ảnh hưởng correctness, phát `WARNING` hoặc `ERROR` thích hợp, gắn với `Element` khi có thể.
9. **Không nhầm version:** `--release` chọn source target; `@SupportedSourceVersion` công bố khả năng processor; `latestSupported()` không tự bảo đảm tương thích.
10. **Processor thực sự chạy:** kiểm tra explicit `-processor`/processor path, tránh build xanh do processor bị tắt.
11. **Kiểm thử đa JDK:** chạy trên ma trận compiler/toolchain mà sản phẩm hỗ trợ, bổ sung fixture khi Java thêm constructs mới.
12. **Không lạm dụng preview:** chỉ bật preview khi nghiệp vụ yêu cầu và hệ thống kiểm soát được compiler version, feature flags và vòng đời phát hành.

## 17. Câu hỏi tự kiểm tra

**1.** Processor trước kia chỉ dùng `if (e.getKind() == ElementKind.CLASS)`. Điều gì xảy ra với `record Ticket(...)`?

**Đáp:** `Ticket` có kind `RECORD`, nên bị nhánh `CLASS` bỏ qua. Build có thể vẫn thành công trong khi validation thiếu dữ liệu.

**2.** `defaultAction` và `visitUnknown` có đồng nghĩa?

**Đáp:** Không. `defaultAction` phục vụ những visit methods đã biết nhưng chưa có xử lý riêng trong các simple visitors; `visitUnknown` xử lý element mà visitor chưa nhận diện theo hợp đồng, thường do language model được mở rộng.

**3.** Khi một `SimpleElementVisitor14` chưa override `visitRecordComponent`, có nhất thiết ném lỗi trên record components hiện nay không?

**Đáp:** Không. `SimpleElementVisitor14` đã có method `visitRecordComponent` và implementation mặc định gọi `defaultAction`. Với visitor cũ hơn chưa xử lý cấu trúc này, đường dispatch có thể đưa đến `visitUnknown`. Đừng đánh đồng mọi lớp visitor hoặc mọi version.

**4.** `ElementScanner14` đã in đầy đủ mọi record component nếu chỉ gọi `scan(record)`?

**Đáp:** Scanner có logic duyệt các thành phần con và biết `RecordComponentElement`. Tuy nhiên, nếu subclass override method làm gián đoạn traversal, hoặc logic in/đếm không được implement, có thể không nhận output mong đợi. Kiểm tra bằng assertions trên count và các nodes thực tế.

**5.** Tại sao `@SupportedSourceVersion(RELEASE_17)` không phải lời hứa hỗ trợ Java 26?

**Đáp:** Đây là mức source version được processor công bố hỗ trợ. Để hỗ trợ Java 26 cần kiểm chứng khả năng phân tích các structures liên quan, cập nhật metadata/phần xử lý khi đã đạt.

**6.** Cách nào phù hợp với processor chuyên kiểm tra an toàn khi gặp kind mới chưa hỗ trợ?

**Đáp:** Không được tự động chấm pass. Phát diagnostic `ERROR` hoặc từ chối rõ ràng, cập nhật processor và tests trước khi công bố hỗ trợ mới.

**7.** Khi Java thêm enum constant vào `ElementKind`, có nên giả định `switch` không cần nhánh dự phòng?

**Đáp:** Không. Nên có chính sách fallback/unsupported, và thêm xử lý tường minh khi nghiệp vụ cần hỗ trợ kind mới.

**8.** Code `record` có cần `--enable-preview` trong Java 17 không?

**Đáp:** Không. Record là tính năng chính thức từ Java 16 và hoạt động với `--release 17` trong ví dụ.

**9.** Có thể khẳng định đã kiểm tra mọi element kind tương lai bằng cách gọi `visitor.visitUnknown(currentElement, null)` không?

**Đáp:** Không. Gọi method thủ công chỉ chứng minh nhánh dự phòng thực thi được; nó không xác minh dispatch/hành vi của compiler khi một cấu trúc mới thật sự được thêm. Cần integration test với JDK cung cấp cấu trúc mới.

## Tài liệu chính thức vẫn đang được duy trì

- [Oracle Java SE 26 — `Element`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html): `getKind()`, `accept(...)`, các loại declaration và cảnh báo về `instanceof`.
- [Oracle Java SE 26 — `ElementKind`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): enum kinds và khả năng thêm constants trong tương lai.
- [Oracle Java SE 26 — `ElementVisitor`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/ElementVisitor.html): dispatch và `visitUnknown`.
- [Oracle Java SE 26 — `SimpleElementVisitor14`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/SimpleElementVisitor14.html): `defaultAction` và `visitRecordComponent`.
- [Oracle Java SE 26 — `ElementScanner14`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementScanner14.html): quét các elements con, hỗ trợ record components.
- [Oracle Java SE 26 — `ElementKindVisitor14`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementKindVisitor14.html): phân nhánh visitor theo kind.
- [Oracle Java SE 26 — `TypeElement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/TypeElement.html): `getRecordComponents()` và mô hình record.
- [Oracle Java SE 26 — `AbstractElementVisitor6`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/AbstractElementVisitor6.html): cách `visitUnknown` mặc định phát hiện element chưa biết.
- [Oracle JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): thay đổi mặc định kích hoạt annotation processing.

**Ghi nhớ:** Khi compiler bổ sung một loại khai báo mới, processor có thể **crash** hoặc **bỏ qua dữ liệu mà không báo lỗi**. Thiết kế tương thích cần visitor/scanner đúng thế hệ, nhánh dự phòng `defaultAction` và `visitUnknown` với chính sách nghiệp vụ rõ ràng, kiểm tra `ElementKind` không giả định bất biến, và test thực tế với các constructs mới trên từng JDK được hỗ trợ.
