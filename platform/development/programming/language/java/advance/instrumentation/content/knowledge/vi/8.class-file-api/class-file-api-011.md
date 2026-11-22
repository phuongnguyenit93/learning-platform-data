# Giữ thông tin debug, thuộc tính chuẩn và thuộc tính không nhận diện với Java Class-File API

**Class-File API** (`java.lang.classfile`) cho phép đọc, tạo và biến đổi tệp `.class` bằng mô hình Java có kiểu rõ ràng. Khi dùng API này trong công cụ build hoặc Java agent, việc “giữ nguyên mã chạy được” **chưa đủ**: bản `.class` kết quả có thể cần giữ **dòng mã nguồn, thông tin biến cục bộ, tên tham số, generic signature, annotation, metadata module/record** và cả **attribute riêng của công cụ khác** mà thư viện hiện tại không nhận diện.

Một phép biến đổi tốt phải xác định rõ thuộc tính nào **cần giữ nguyên về mặt ý nghĩa**, thuộc tính nào **phải tính lại khi đổi bytecode**, và thuộc tính nào **không thể bảo đảm an toàn nếu chỉ sao chép payload nhị phân**. Bài này làm rõ các nhóm đó, các option `PASS_*`/`DROP_*` của API, cách xử lý `UnknownAttribute` và một thí nghiệm Java 24+ chạy được để chứng minh kết quả.

> **Yêu cầu phiên bản:** Class-File API được chuẩn hóa trong **JDK 24 (JEP 484)**. Nó từng ở dạng preview trong JDK 22/23, và **không có trong Java 17**. Ví dụ thao tác `java.lang.classfile` dưới đây cần **JDK 24 trở lên**, không dùng `--enable-preview`. Một class mục tiêu bình thường vẫn có thể được biên dịch cho Java 17, nhưng chương trình dùng API này phải biên dịch và chạy trên JDK hỗ trợ.

## 1. Attribute là gì và tại sao cần giữ?

Một tệp `.class` không chỉ chứa opcode. Theo JVMS §4, các cấu trúc như class, field, method, phần `Code` và record component có thể kèm các **attribute**. Mỗi attribute trong định dạng nhị phân có tên (qua một mục `CONSTANT_Utf8`), chiều dài và payload. Tên do JVM quy định cho attribute chuẩn; công cụ cũng có thể tạo tên riêng mà JVM không biết cách giải mã.

```text
ClassFile
  ├── constant_pool
  ├── this_class / super_class / interfaces
  ├── fields[]
  │    └── attributes[]                 ví dụ ConstantValue, Signature
  ├── methods[]
  │    ├── attributes[]                 ví dụ Code, MethodParameters
  │    └── Code
  │         ├── bytecode
  │         ├── exception_table
  │         └── attributes[]            ví dụ LineNumberTable, LocalVariableTable
  └── attributes[]                      ví dụ SourceFile, RuntimeVisibleAnnotations
```

Ví dụ `javac -g -parameters Sample.java` có thể tạo các metadata sau:

- **`SourceFile`**: tên tệp nguồn, hữu ích khi trình bày stack trace hoặc ánh xạ nguồn.
- **`LineNumberTable`**: ánh xạ vị trí bytecode sang số dòng nguồn. Debugger và stack trace có thể dùng dữ liệu này.
- **`LocalVariableTable`**: tên và kiểu biến cục bộ cùng phạm vi sống; thường dùng bởi debugger.
- **`LocalVariableTypeTable`**: thông tin kiểu tổng quát của biến cục bộ, thường xuất hiện nếu có biến generic phù hợp và compiler phát ra metadata.
- **`MethodParameters`**: tên/cờ của tham số khai báo; được điều khiển bởi `-parameters` khi dùng `javac`, và khác `LocalVariableTable`. Reflection có thể sử dụng nó.
- **`Signature`**: generic signature của class, field hoặc method. Xóa nhầm có thể làm mất thông tin generic mà reflection/framework sử dụng.
- **`RuntimeVisibleAnnotations` và các attribute annotation khác**: có thể ảnh hưởng trực tiếp đến reflection và framework như DI, validation, serialization.
- **`StackMapTable`**: dữ liệu xác minh kiểu của JVM. Đây **không chỉ là metadata debug**; làm mất hoặc ghi sai có thể khiến class không verify được.
- **Thuộc tính không nhận diện**: phần mở rộng của compiler, coverage tool, profiler hoặc framework. Parser không biết payload có nghĩa gì, nhưng bên tạo attribute có thể phụ thuộc vào nó.

Khi biến đổi class, mục tiêu không phải “giữ tất cả bytes trong file không đổi”. Mục tiêu là **giữ các ý nghĩa cần thiết**, đồng thời tái xây dựng những chỉ số tham chiếu và offset bị ảnh hưởng bởi thay đổi.

## 2. Phân biệt ba nhóm metadata

| Nhóm | Ví dụ | Hệ quả nếu làm mất / ghi sai |
| --- | --- | --- |
| **Thông tin debug** | `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`, `SourceFile`, `SourceDebugExtension` | Có thể mất số dòng/tên biến/phạm vi hoặc thông tin ánh xạ nguồn; code có thể vẫn chạy nhưng khó debug. |
| **Thuộc tính chuẩn có ý nghĩa chương trình/JVM** | `Signature`, `MethodParameters`, `RuntimeVisibleAnnotations`, `Exceptions`, `NestHost`, `Record`, `PermittedSubclasses`, `StackMapTable` | Có thể mất metadata cần cho reflection, framework, ngữ nghĩa của class hoặc tính hợp lệ khi xác minh/liên kết. |
| **Thuộc tính không nhận diện** | Tên riêng như `VendorTrace`, `ToolMarker`, `MysteryTag` | API chỉ nhìn thấy tên + payload; giữ bytes có thể cần thiết cho công cụ khác, nhưng payload cũng có thể chứa chỉ số đã lỗi thời sau transform. |

**Không được đồng nhất “không phải opcode” với “không quan trọng”.** Xóa `LineNumberTable` có thể không ảnh hưởng hành vi chạy nhưng làm stack trace thiếu dòng; xóa `RuntimeVisibleAnnotations` có thể thay đổi hành vi framework; còn can thiệp sai `StackMapTable` có thể gây `VerifyError`.

Tương tự, **`MethodParameters` không phải `LocalVariableTable`**. Việc yêu cầu loại bỏ debug pseudo-instructions bằng `DROP_DEBUG` không có nghĩa mọi thông tin về tham số, annotation hoặc `SourceFile` cũng bị xóa.

## 3. Cách Class-File API mô hình hóa attribute

API đọc bytes thành mô hình:

```java
// Mã minh họa trong phương thức; bytes là byte[] của một class hợp lệ.
ClassFile cf = ClassFile.of();
ClassModel model = cf.parse(bytes);
List<Attribute<?>> classAttributes = model.attributes();
```

Mã minh họa cần các import `java.lang.classfile.ClassFile`, `ClassModel`, `Attribute` và `java.util.List`. Phần `ClassModel` cung cấp cả danh sách field/method, model con và phép duyệt qua các `ClassElement`.

Có **hai cách nhìn** quan trọng:

1. **Attribute có mô hình riêng**: ví dụ `SourceFileAttribute`, `SignatureAttribute`, `RuntimeVisibleAnnotationsAttribute`, `UnknownAttribute`. Có thể kiểm tra qua `model.attributes()` hoặc tìm bằng mapper tương ứng (`findAttribute(...)`).
2. **Thông tin được “trải” vào mô hình liên quan**: `LineNumberTable` không đơn giản là một `ClassElement`; các dòng xuất hiện dưới dạng pseudo-instruction `LineNumber` trong `CodeModel`. Tương tự, các mục của `LocalVariableTable` được duyệt như `LocalVariable`; các mục của `LocalVariableTypeTable` là `LocalVariableType`. `BootstrapMethods` cũng có biểu diễn gắn với constant pool. Không thể bảo đảm giữ chúng chỉ bằng cách duyệt mỗi attribute cấp class rồi ghi lại.

Ví dụ Java 24+ để đếm debug pseudo-instructions:

```java
// model: ClassModel đọc từ ClassFile.of(...).parse(bytes)
// Đoạn minh họa bên trong phương thức, cần import LineNumber, LocalVariable.
long lineEntries = model.methods().stream()
    .flatMap(method -> method.code().stream())
    .flatMap(code -> code.elementStream())
    .filter(element -> element instanceof LineNumber)
    .count();

long localEntries = model.methods().stream()
    .flatMap(method -> method.code().stream())
    .flatMap(code -> code.elementStream())
    .filter(element -> element instanceof LocalVariable)
    .count();
```

Các pseudo-instruction này được hiển thị hay loại khỏi traversal tùy **options** của `ClassFile` context. Không phải mọi method đều có `Code` (ví dụ abstract/native), nên `method.code()` trả `Optional<CodeModel>`.

## 4. Các tùy chọn bảo toàn trong `ClassFile.of(...)`

Một cấu hình có chủ đích để **ưu tiên giữ** metadata:

```java
ClassFile preserving = ClassFile.of(
    ClassFile.DebugElementsOption.PASS_DEBUG,
    ClassFile.LineNumbersOption.PASS_LINE_NUMBERS,
    ClassFile.AttributesProcessingOption.PASS_ALL_ATTRIBUTES
);
```

Cấu hình này phù hợp khi bạn cần giữ dữ liệu hiện có, nhưng nó **không thay thế bước kiểm tra tính hợp lệ** nếu bytecode, cấu trúc class hoặc constant pool thay đổi.

| Option | Ý nghĩa |
| --- | --- |
| `DebugElementsOption.PASS_DEBUG` | Cho phép xử lý các debug pseudo-instruction như `LocalVariable`, `LocalVariableType`, `CharacterRange`. Đây là mặc định. |
| `DebugElementsOption.DROP_DEBUG` | Bỏ những pseudo-instruction debug đó khỏi traversal và builder khi cấu trúc liên quan được xử lý. |
| `LineNumbersOption.PASS_LINE_NUMBERS` | Giữ các phần tử `LineNumber` khi xử lý `CodeModel`. Đây là mặc định. |
| `LineNumbersOption.DROP_LINE_NUMBERS` | Bỏ `LineNumber` khỏi traversal và builder; không làm bytecode thực thi ngừng hoạt động. |
| `AttributesProcessingOption.PASS_ALL_ATTRIBUTES` | Cố gắng giữ các original attributes khi transform, kể cả loại chưa thể kiểm tra tính ổn định; đây là mặc định. |
| `AttributesProcessingOption.DROP_UNKNOWN_ATTRIBUTES` | Loại các attribute có dependency được phân loại `AttributeStability.UNKNOWN` khi transform. |
| `AttributesProcessingOption.DROP_UNSTABLE_ATTRIBUTES` | Loại các attribute có dependency từ mức `UNSTABLE` trở lên (bao gồm nhóm `UNKNOWN`) khi transform. |

Hai loại option **debug** và **attribute stability** là các quyết định khác nhau. Ví dụ, có thể yêu cầu giữ debug pseudo-instructions nhưng bỏ unknown attributes. Hoặc có thể giữ mọi attribute cấp class nhưng loại line numbers trong code. Đừng gọi chung mọi thứ là “debug attributes”.

### 4.1. Default “PASS” không bảo đảm mọi phép transform đều giữ được dữ liệu

Class-File API cho phép transform bằng cách đưa từng element vào builder:

```java
ClassFile cf = ClassFile.of();
ClassModel source = cf.parse(inputBytes);
byte[] result = cf.transformClass(source, ClassTransform.ACCEPT_ALL);
```

`ClassTransform.ACCEPT_ALL` truyền các phần tử cấp class qua builder. Khi thư viện thấy cấu trúc không thay đổi, nó có thể tối ưu bằng cách **sao chép nguyên một vùng bytes** thay vì bung ra từng code element (*bulk copy*). Ngược lại, khi biến đổi method body, việc xử lý `CodeModel` sẽ đi qua các phần tử dòng/biến/nhãn và áp dụng các option debug.

Vì vậy **`DROP_DEBUG` không phải một công tắc toàn cục kiểu “xóa mọi mục debug trong bất kỳ file output nào”**. Nếu code body được bulk-copy nguyên khối, kết quả vẫn có thể giữ debug attributes của khối đó. Để chủ ý loại các pseudo-instruction, cần yêu cầu transform **thực sự đi vào method bodies**, chẳng hạn:

```java
ClassFile drop = ClassFile.of(
    ClassFile.DebugElementsOption.DROP_DEBUG,
    ClassFile.LineNumbersOption.DROP_LINE_NUMBERS
);

byte[] withoutCodeDebug = drop.transformClass(
    drop.parse(originalBytes),
    ClassTransform.transformingMethodBodies(CodeTransform.ACCEPT_ALL)
);
```

Ở đây `CodeTransform.ACCEPT_ALL` vẫn giữ các code element **được trình bày cho nó**, còn các loại debug đã bị option loại khỏi traversal. Sự khác nhau giữa **bulk-copy** và **explode/rebuild** là điều cần nhớ khi kiểm tra metadata sau transform.

### 4.2. Attribute được “giữ” nhưng có thể không còn đúng

Attribute chuẩn thường có **mapper** hiểu constant pool, label hoặc cấu trúc liên quan. Khi API tái xây dựng, mapper có thể cập nhật những chỉ số được mô hình hóa.

Với attribute **không nhận diện**, payload chỉ là bytes mờ đục. API không thể tự biết payload có chứa:

- Index vào constant pool (ví dụ trỏ tới tên/descriptor);
- Offset bytecode hoặc index của exception handler;
- Chỉ số field/method/interface đã được đổi thứ tự;
- Thông tin phiên bản, checksum hoặc bố cục riêng của compiler/tool.

Nếu đổi constant pool hoặc xê dịch bytecode mà chỉ copy payload, attribute có thể **còn tồn tại về mặt nhị phân nhưng sai ý nghĩa**. Bởi vậy `PASS_ALL_ATTRIBUTES` là chính sách **giữ thông tin**, không phải lời hứa tự động remap mọi định dạng lạ.

## 5. Thuộc tính chuẩn: giữ đúng cấu trúc, không chỉ sao chép tên

Khi biến đổi method body, metadata có tham chiếu đến **vị trí lệnh** cần được xử lý cùng thay đổi mã.

| Attribute / mô hình | Phụ thuộc điển hình | Cách giữ an toàn |
| --- | --- | --- |
| `LineNumberTable` → `LineNumber` | Vị trí bytecode tương ứng dòng nguồn | Giữ/cập nhật các line entry theo lệnh mới; đừng bê nguyên offset cũ nếu thêm lệnh. |
| `LocalVariableTable` → `LocalVariable` | Slot + nhãn bắt đầu/kết thúc phạm vi | Giữ label scope hợp lệ; cập nhật phạm vi và slot khi đổi mã/biến cục bộ. |
| `LocalVariableTypeTable` → `LocalVariableType` | Tương tự local-variable scope, kèm generic signature | Giữ đồng bộ với LocalVariableTable và descriptor/signature khi còn áp dụng. |
| `StackMapTable` | Frame/kiểu tại các vị trí liên quan control flow | Để API tái dựng stack maps khi thích hợp, hoặc cung cấp frame chính xác với cấu hình rõ ràng; xác minh output trên JVM. |
| `SourceFile` / `SourceDebugExtension` | Tên nguồn / dữ liệu ánh xạ nguồn | Giữ nếu còn mô tả đúng code; đổi tên/gộp nguồn có thể đòi cập nhật. |
| `MethodParameters` | Tên và cờ tham số phương thức | Giữ nếu descriptor/chữ ký phương thức không đổi; nếu đổi signature phải cập nhật cho khớp. |
| `Signature` | Generic signature của class, field, method | Giữ khi còn đúng sau transform; không đánh đồng với JVM descriptor. |
| `RuntimeVisibleAnnotations` / type annotations | Chủ thể được gắn annotation, đôi khi index/offset/target | Kiểm tra vị trí và tính đúng sau khi đổi code hay các danh sách thành viên. |
| `Record`, `NestHost`, `NestMembers`, `PermittedSubclasses` | Quan hệ cấu trúc giữa các class/thành viên | Không tùy ý xóa hoặc giữ metadata đã không còn phù hợp với class được xây dựng. |

**Ví dụ:** nếu instrument phương thức bằng cách chèn lệnh mới đầu method, một `LineNumberTable` chỉ lưu offset tuyệt đối từ bản cũ có thể chỉ nhầm lệnh; Class-File API biểu diễn line number và local-variable scope thông qua code elements/labels để hỗ trợ tái tạo tương ứng. Bạn vẫn cần xác định **dòng nguồn nào hợp lý** cho lệnh instrumentation mới: không có một phép đoán tuyệt đối đúng cho mọi framework.

**Chú ý:** `StackMapTable` và `BootstrapMethods` được API xử lý đặc biệt, không phải lúc nào cũng xuất hiện như một element đơn giản để tự `with(attribute)` từ mọi cấp. Nên dùng các builder/transform phù hợp với model thay vì tự copy một khối bytes attribute và hy vọng chỉ số còn đúng.

## 6. Thuộc tính không nhận diện: `UnknownAttribute` là gì?

Khi gặp attribute không có mapper trong `Attributes` và cũng không có mapper tùy chỉnh được đăng ký, Class-File API có thể biểu diễn nó thành `UnknownAttribute`.

Các thao tác cơ bản:

```java
// Mã minh họa với một ClassModel có attribute lạ ở cấp class.
for (Attribute<?> attr : model.attributes()) {
    if (attr instanceof UnknownAttribute unknown) {
        System.out.println(unknown.attributeName().stringValue()
                + " payloadBytes=" + unknown.contents().length);
    }
}
```

Ý nghĩa:

- `attributeName()` trả tên attribute trong constant pool.
- `contents()` trả phần payload **không được giải nghĩa**; nhìn thấy một mảng byte không cho phép kết luận format hay dependency của nó.
- `UnknownAttribute` không phải “attribute hỏng”; nó có thể là metadata hợp lệ mà một công cụ khác hiểu và JVM bỏ qua theo quy tắc class-file.
- Việc unknown có thể xuất hiện ở những cấp nào phụ thuộc version API và cấu trúc class-file. Trong JDK 24, tài liệu `UnknownAttribute` nêu không chuyển nó như phần tử của traversal `CodeModel`; không được khẳng định chỉ duyệt code elements là bắt hết mọi attribute lạ.

### 6.1. Ba chiến lược xử lý unknown

**Giữ nguyên (`PASS_ALL_ATTRIBUTES`)** khi bạn không đổi những cấu trúc mà payload có thể tham chiếu, muốn bảo toàn metadata của công cụ khác, và chấp nhận rằng payload chưa được xác minh ngữ nghĩa. Đây là mặc định, phù hợp cho phép transform rất nhỏ hoặc round-trip có kiểm tra.

**Loại bỏ (`DROP_UNKNOWN_ATTRIBUTES`)** khi đầu ra không cần định dạng lạ và rủi ro giữ payload với index/offset lỗi thời lớn hơn rủi ro mất metadata. Phải hiểu rằng công cụ khác có thể cần attribute ấy; việc JVM chạy vẫn đúng không chứng minh dữ liệu bên ngoài còn đủ.

**Định nghĩa mapper tùy chỉnh (`AttributeMapperOption.of(...)`)** nếu bạn biết rõ định dạng riêng: viết `AttributeMapper` và `CustomAttribute` tương ứng, mô hình hóa những index/label, cấu trúc áp dụng, multiplicity và stability của attribute để API có dữ liệu cập nhật đúng. Đây là hướng đi bền vững khi công cụ của bạn **sở hữu** metadata đó hoặc phải bảo toàn hợp đồng của nó.

Lưu ý mapper tùy chỉnh có độ ưu tiên thấp hơn mapper chuẩn của `Attributes`; không dùng nó để ghi đè ý nghĩa của một attribute chuẩn có sẵn trong JDK.

## 7. Thí nghiệm JDK 24+: quan sát giữ, bỏ debug và giữ/bỏ unknown

Thí nghiệm gồm hai file Java, không cần Maven/Gradle hay thư viện ngoài. Ta dùng một class nhỏ được biên dịch với `-g -parameters`, rồi một chương trình Class-File API phân tích và round-trip:

1. **Bản gốc:** có `SourceFile`, `RuntimeVisibleAnnotations`, `MethodParameters`, `LineNumberTable` và `LocalVariableTable`.
2. **Round-trip mặc định:** `ClassTransform.ACCEPT_ALL` giữ các metadata đang có.
3. **Fixture unknown:** trên một **bản sao** bytes để thử nghiệm, đổi **tên UTF8 của attribute `SourceFile`** thành tên lạ cùng độ dài `MysteryTag`. Đây là biến đổi riêng để tạo fixture kiểm tra, không dùng làm công cụ sửa class file production.
4. **`PASS_ALL_ATTRIBUTES`:** fixture vẫn có `MysteryTag` sau transform.
5. **`DROP_UNKNOWN_ATTRIBUTES`:** fixture không còn `MysteryTag` sau transform.
6. **`DROP_DEBUG + DROP_LINE_NUMBERS` và đi qua `CodeModel`:** các pseudo-instruction debug bị bỏ, trong khi `SourceFile`, annotation và `MethodParameters` vẫn có.

### 7.1. `Sample.java` — class đầu vào

```java
@Deprecated
public class Sample {
    public static int sum(int left, int right) {
        int total = left + right;
        return total;
    }
}
```

`@Deprecated` ở class tạo metadata annotation phù hợp trong class file; `-parameters` giữ tên tham số của `sum`; `-g` yêu cầu javac phát đầy đủ metadata debug được hỗ trợ. Constructor mặc định vẫn có code và line number. Tệp tên đúng `Sample.java`.

### 7.2. `AttributeInspector.java` — chương trình Class-File API đầy đủ

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.attribute.SourceFileAttribute;
import java.lang.classfile.attribute.RuntimeVisibleAnnotationsAttribute;
import java.lang.classfile.attribute.MethodParametersAttribute;
import java.lang.classfile.attribute.UnknownAttribute;
import java.lang.classfile.instruction.LineNumber;
import java.lang.classfile.instruction.LocalVariable;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class AttributeInspector {
    private static final ClassFile KEEP = ClassFile.of(
            ClassFile.DebugElementsOption.PASS_DEBUG,
            ClassFile.LineNumbersOption.PASS_LINE_NUMBERS,
            ClassFile.AttributesProcessingOption.PASS_ALL_ATTRIBUTES);

    public static void main(String[] args) throws Exception {
        byte[] original = Files.readAllBytes(Path.of("Sample.class"));
        byte[] same = KEEP.transformClass(
                KEEP.parse(original), ClassTransform.ACCEPT_ALL);
        byte[] unknown = renamedAttributeFixture(original);

        byte[] withUnknown = KEEP.transformClass(
                KEEP.parse(unknown), ClassTransform.ACCEPT_ALL);

        ClassFile dropUnknown = ClassFile.of(
                ClassFile.AttributesProcessingOption.DROP_UNKNOWN_ATTRIBUTES);
        byte[] withoutUnknown = dropUnknown.transformClass(
                dropUnknown.parse(unknown), ClassTransform.ACCEPT_ALL);

        ClassFile dropDebug = ClassFile.of(
                ClassFile.DebugElementsOption.DROP_DEBUG,
                ClassFile.LineNumbersOption.DROP_LINE_NUMBERS);
        byte[] withoutDebug = dropDebug.transformClass(
                dropDebug.parse(original),
                ClassTransform.transformingMethodBodies(CodeTransform.ACCEPT_ALL));

        print("original", original);
        print("roundTrip", same);
        print("unknownFixture", unknown);
        print("keepUnknown", withUnknown);
        print("dropUnknown", withoutUnknown);
        print("dropDebug", withoutDebug);
    }

    private static void print(String label, byte[] bytes) {
        ClassModel model = KEEP.parse(bytes);
        boolean source = model.attributes().stream()
                .anyMatch(a -> a instanceof SourceFileAttribute);
        boolean annotations = model.attributes().stream()
                .anyMatch(a -> a instanceof RuntimeVisibleAnnotationsAttribute);
        boolean parameters = model.methods().stream()
                .flatMap(m -> m.attributes().stream())
                .anyMatch(a -> a instanceof MethodParametersAttribute);
        long lines = model.methods().stream()
                .flatMap(m -> m.code().stream())
                .flatMap(c -> c.elementStream())
                .filter(e -> e instanceof LineNumber).count();
        long locals = model.methods().stream()
                .flatMap(m -> m.code().stream())
                .flatMap(c -> c.elementStream())
                .filter(e -> e instanceof LocalVariable).count();
        long unknown = model.attributes().stream()
                .filter(a -> a instanceof UnknownAttribute &&
                        a.attributeName().stringValue().equals("MysteryTag"))
                .count();
        System.out.printf(
                "%s source=%s annotations=%s parameters=%s lines=%d locals=%d unknown=%d%n",
                label, source, annotations, parameters, lines, locals, unknown);
    }

    private static byte[] renamedAttributeFixture(byte[] input) {
        byte[] bytes = input.clone();
        byte[] from = "SourceFile".getBytes(StandardCharsets.US_ASCII);
        byte[] to = "MysteryTag".getBytes(StandardCharsets.US_ASCII);
        int count = 0;
        for (int i = 0; i <= bytes.length - from.length; i++) {
            boolean matches = true;
            for (int j = 0; j < from.length; j++) {
                if (bytes[i + j] != from[j]) {
                    matches = false;
                    break;
                }
            }
            if (matches) {
                System.arraycopy(to, 0, bytes, i, to.length);
                count++;
            }
        }
        if (count != 1) {
            throw new IllegalStateException(
                    "Unexpected SourceFile markers: " + count);
        }
        return bytes;
    }
}
```

Đoạn mã trên dùng API chuẩn của **JDK 24+** và là chương trình độc lập. Không cần khai báo module hay `--add-modules` khi biên dịch hai file trên bằng JDK đầy đủ.

**Vì sao fixture hợp lệ cho bài thử?** Với class mẫu này, tên UTF8 `SourceFile` có đúng một lần xuất hiện và hai tên `SourceFile`/`MysteryTag` đều dài **10 byte ASCII**. Thay payload UTF8 của **tên attribute** mà không đổi length làm class-level `SourceFile` trở thành attribute chưa biết có tên `MysteryTag`. Nó chỉ nhằm kiểm tra chính sách **pass/drop**; payload bên trong vẫn có cấu trúc gốc của `SourceFile`, vì vậy không được suy ra đây là định dạng nghiệp vụ `MysteryTag` thực sự. Nếu thay source/compile khiến tên xuất hiện nhiều lần, guard `count != 1` buộc dừng.

Không được áp dụng thao tác tìm/sửa chuỗi bytes này cho mọi class file ngoài thử nghiệm. Mọi sửa đổi class file thật nên đi qua mô hình phù hợp và xử lý đúng constant pool.

### 7.3. Biên dịch và chạy

Đặt hai file trong cùng một thư mục mới rồi chạy bằng **JDK 24 hoặc mới hơn**:

```bash
javac -version
javac -g -parameters Sample.java
javac AttributeInspector.java
java AttributeInspector
```

Tùy chọn `-g` của `javac` bật thông tin dòng nguồn và biến cục bộ; `-parameters` bật metadata tham số. Lệnh `javac AttributeInspector.java` phải dùng JDK 24+ vì import `java.lang.classfile` không có trong Java 17. Trên Windows PowerShell, các lệnh này cũng chạy trực tiếp khi JDK được cấu hình trong `PATH`.

**Stdout đã kiểm chứng trên OpenJDK 24.0.2** (không có JVM agent khác can thiệp vào file thử nghiệm):

```text
original source=true annotations=true parameters=true lines=3 locals=4 unknown=0
roundTrip source=true annotations=true parameters=true lines=3 locals=4 unknown=0
unknownFixture source=false annotations=true parameters=true lines=3 locals=4 unknown=1
keepUnknown source=false annotations=true parameters=true lines=3 locals=4 unknown=1
dropUnknown source=false annotations=true parameters=true lines=3 locals=4 unknown=0
dropDebug source=true annotations=true parameters=true lines=0 locals=0 unknown=0
```

Bảng giải thích đầu ra:

| Dòng | Điều được chứng minh |
| --- | --- |
| `original` | Class có metadata chuẩn/debug; chưa có attribute lạ. |
| `roundTrip` | `ClassTransform.ACCEPT_ALL` giữ thông tin của class mẫu khi round-trip. |
| `unknownFixture` | Tên `SourceFile` được đổi thành `MysteryTag` trên **bản sao**, nên `source=false`, `unknown=1`; annotation, parameters, line và local variable vẫn còn. |
| `keepUnknown` | `PASS_ALL_ATTRIBUTES` giữ lại một `UnknownAttribute` trong trường hợp kiểm soát này. |
| `dropUnknown` | `DROP_UNKNOWN_ATTRIBUTES` loại `MysteryTag` khỏi kết quả. |
| `dropDebug` | Khi ép duyệt và xây lại code bodies, `DROP_DEBUG`/`DROP_LINE_NUMBERS` loại local-variable và line pseudo-instructions; attribute chuẩn khác vẫn còn. |

**Tại sao `lines=3` và `locals=4`?** Với `javac 24.0.2` và class mẫu này, có ba line-number entry (bao gồm constructor và phương thức `sum`) và bốn local-variable entry (`this` trong constructor, cộng `left`, `right`, `total` trong `sum`). Đây là kết quả của cấu hình/compiler cụ thể; khi thay source hoặc version compiler, số đếm có thể khác. Bảo đảm cốt lõi của thí nghiệm là quan hệ **giữ nguyên so với bản gốc / loại khỏi bản xử lý lại**, không phải ghi nhớ số lượng entry.

**Điểm dễ bỏ sót nhất:** mặc dù bản `dropDebug` không còn `LineNumber`/`LocalVariable`, nó vẫn có `SourceFile` và `MethodParameters`. Bạn cần chọn chính sách bảo toàn cho **từng loại metadata**, không thể giả định một option xóa mọi thứ liên quan tới việc debug.

### 7.4. Kiểm tra thêm bằng `javap`

Trên class ban đầu:

```bash
javap -v -p Sample
javap -l -p Sample
```

Bạn có thể tìm các mục `SourceFile`, `RuntimeVisibleAnnotations`, `MethodParameters`, `LineNumberTable`, `LocalVariableTable`. Lưu ý chương trình `AttributeInspector` trong bài chỉ giữ kết quả transform **trong các mảng `byte[]`**, chưa ghi chúng thành file. Vì vậy chạy `javap Sample` vẫn cho dữ liệu của `Sample.class` **gốc**; nó không thể tự hiển thị mảng `withUnknown` hoặc `withoutDebug` trong bộ nhớ. Muốn dùng `javap` với output transform, bạn phải chủ động ghi bytes đó ra một file và phân tích file ấy.

Trong ứng dụng thực tế, sau transform còn nên chạy `ClassFile.verify(...)`, test class loading và hành vi của framework/reflection để bảo đảm output có metadata **đúng**, không chỉ chứa những tên attribute trông giống ban đầu.

## 8. Cách làm việc với custom attribute có định dạng đã biết

Nếu một công cụ bổ sung attribute riêng, ví dụ `TraceSpanMap` chứa offset bytecode, có hai tình huống:

**Chỉ cần truyền qua**: bạn không đổi code layout/constant pool hoặc biết chính sách dữ liệu cho phép giữ payload nguyên trạng. Có thể dùng `PASS_ALL_ATTRIBUTES` và `ClassTransform.ACCEPT_ALL`, rồi kiểm tra attribute còn được ghi ra file. Đây là chiến lược thực dụng cho transform không chạm đến cấu trúc liên quan.

**Phải thay đổi code/constant pool**: chỉ giữ `byte[]` cũ không bảo đảm offset/index còn đúng. Lúc này nên mô hình hóa `TraceSpanMap` bằng **custom `AttributeMapper`**. Mapper đọc/writer hiểu cấu trúc, gắn dữ liệu với model thích hợp và khai báo tính ổn định của attribute. Có thể đăng ký mapper bằng:

```java
// Mã minh họa API, không phải chương trình độc lập.
// customMapperResolver là Function<Utf8Entry, AttributeMapper<?>> đã triển khai.
ClassFile cf = ClassFile.of(
    ClassFile.AttributeMapperOption.of(customMapperResolver)
);
```

Custom mapper phải trả `null` nếu không nhận diện tên được hỏi, và tên mapper trả về phải khớp tên đang phân tích. Không tùy tiện khai báo một payload không hiểu là “stable”: nếu chứa code offset hoặc constant-pool index, tính ổn định phụ thuộc thao tác chuyển đổi của bạn.

**Chú ý về backward/forward compatibility:** Một JDK có thể bổ sung attribute chuẩn mới trong tương lai. Nếu parser dùng `UnknownAttribute` để giữ attribute ấy, phần dữ liệu có thể có ý nghĩa với JVM đời mới hơn. Nếu công cụ của bạn **buộc phải hiểu toàn bộ cấu trúc** mới được phép sửa, nên kiểm tra major version và loại element, rồi từ chối xử lý an toàn khi không hiểu. Nếu bạn chỉ đổi một phần nhỏ, có thể pass-through các phần còn lại theo hợp đồng và QA thích hợp.

## 9. Trong Java agent: nên xử lý `classfileBuffer` như thế nào?

Một `ClassFileTransformer` có thể dùng Class-File API trực tiếp trên mảng `classfileBuffer` do JVM đưa vào. Mã dưới đây **chỉ minh họa ý tưởng**, chưa phải class agent độc lập:

```java
// Trong ClassFileTransformer.transform(...) trên JDK 24+:
if (!"demo/example/Target".equals(className)) {
    return null;
}

ClassFile cf = ClassFile.of(
    ClassFile.DebugElementsOption.PASS_DEBUG,
    ClassFile.LineNumbersOption.PASS_LINE_NUMBERS,
    ClassFile.AttributesProcessingOption.PASS_ALL_ATTRIBUTES
);
ClassModel input = cf.parse(classfileBuffer);
byte[] output = cf.transformClass(input, ClassTransform.ACCEPT_ALL);
return output;
```

Đây là ví dụ **round-trip** không sửa logic. Trong agent thật, khi có code transform, thay `ClassTransform.ACCEPT_ALL` bằng transform của bạn và **bảo toàn tất cả element không chủ ý thay đổi**. Không sửa trực tiếp mảng `classfileBuffer` do JVM cung cấp. Nếu không muốn biến đổi gì, trả `null` còn đơn giản và rẻ hơn việc tạo lại classfile.

Vì có thể tồn tại **nhiều agent/transformer**, `classfileBuffer` không nhất thiết là bản class trên ổ đĩa: một transformer phía trước đã có thể thay đổi metadata. Bạn cần **phân tích bytes tại callback**, không tải lại `.class` từ resource rồi ghi đè lên chuỗi xử lý của agent khác.

Khi cần retransform/redefine class đã chạy, các giới hạn thay đổi cấu trúc JVM vẫn áp dụng. Tài liệu về attribute preservation không tự cấp quyền thêm/xóa field/method trong lớp đã nạp. Thay đổi vị trí lệnh hoặc stack maps còn cần được xác minh lại trên class output thực tế.

## 10. QA trước khi phát hành class file đã transform

Sau khi build ra `byte[]` hoặc `.class` mới, nên kiểm tra ở **ba cấp**:

### 10.1. Cấp cấu trúc

- Parse output bằng `ClassFile.of().parse(output)` và duyệt **class, field, method, code**; so sánh danh sách attribute liên quan với input.
- Đếm/so sánh `LineNumber`, `LocalVariable`, `LocalVariableType` hoặc kiểm tra trực tiếp các attribute tương ứng khi cần; không chỉ đếm tổng số attribute ở cấp class.
- Kiểm tra `SourceFile`, `MethodParameters`, `Signature`, annotation, `Record`, `Nest*` và các attribute bắt buộc khác có còn hợp lệ với cấu trúc mới.
- Với unknown/custom attribute, ghi **tên, vị trí gắn, độ dài và checksum** để quan sát khác biệt; chỉ giữ checksum nguyên chưa chứng minh payload vẫn đúng sau đổi constant pool/code offset.
- Không dùng `Arrays.equals(input, output)` làm tiêu chuẩn duy nhất. Class file sau transform có thể được sắp xếp lại constant pool và vẫn giữ hành vi tương đương.

### 10.2. Cấp JVM

- Sử dụng `ClassFile.verify(output)` khi thích hợp và nạp/chạy class output trên phiên bản JVM mục tiêu.
- Với code đã instrument, test các nhánh exception, method phức tạp, generic signatures, class nested, record và class có annotation.
- Khi stack maps được tái tạo, kiểm tra verifier thực tế; `VerifyError`/`ClassFormatError` là dấu hiệu output chưa hợp lệ, không phải lỗi có thể bỏ qua vì “chỉ là debug”.
- Kiểm tra class file version và các thay đổi cấu trúc hợp lệ nếu định nghĩa lại class đã nạp.

### 10.3. Cấp công cụ người dùng

- Mở debugger, đặt breakpoint tại dòng nguồn đúng và kiểm tra stack trace còn line number.
- Xem local variables và tên tham số khi bộ công cụ cần chúng.
- Kiểm tra reflection/framework vẫn thấy annotation và generic/method-parameter metadata dự kiến.
- Nếu phần mềm thứ ba đọc unknown/custom attribute, chạy **bài kiểm thử tích hợp của công cụ đó**; giữ payload theo byte chưa đủ để bảo đảm công cụ vẫn hiểu khi index hoặc offset đã đổi.

## 11. Các lỗi hay gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp và cách xử lý |
| --- | --- |
| Class chạy được nhưng stack trace thiếu số dòng | `LineNumberTable` bị loại hoặc xây lại sai; kiểm tra `PASS_LINE_NUMBERS` và code transform. |
| Debugger không thấy tên biến | Kiểm tra `-g` lúc biên dịch và `LocalVariableTable`/`PASS_DEBUG`; code được obfuscate có thể làm tên mất ngay từ nguồn. |
| Tên tham số reflection mất dù còn local-variable info | `MethodParameters` khác `LocalVariableTable`; kiểm tra `-parameters` và cách pass-through method attributes. |
| Generic metadata bị mất | Kiểm tra `Signature` và các attribute liên quan; đừng chỉ so sánh descriptor JVM. |
| Annotation biến mất sau transform | Kiểm tra `RuntimeVisibleAnnotations`/type annotations và các vị trí áp dụng; không thể xem annotation là metadata debug có thể bỏ tùy ý. |
| `DROP_DEBUG` được bật nhưng output vẫn có line/local table | Có thể code body được bulk-copy; thử đi qua `CodeTransform` để xử lý pseudo-instructions và kiểm tra lại. |
| `DROP_UNKNOWN_ATTRIBUTES` không xóa attribute chuẩn | Đúng theo phạm vi của option: nó nhắm loại có stability `UNKNOWN`; muốn loại thuộc tính chuẩn phải dùng chính sách/transform phù hợp. |
| Unknown attribute vẫn tồn tại nhưng công cụ đọc báo lỗi | Payload có thể chứa constant-pool index/code offset lỗi thời; cần mapper có hiểu format hoặc chính sách không truyền qua. |
| Sau đổi bytecode xuất hiện `VerifyError` | Cần kiểm tra code flow, stack map frames, nhãn/offset/exception handlers, cấu trúc class và JVM target. |
| Chỉ xem `ClassModel.attributes()` mà không thấy `LineNumberTable` | Line number được mô hình hóa như `LineNumber` trong `CodeModel`; phải duyệt đúng cấp. |
| So sánh class sau transform byte-for-byte không bằng bản cũ | Có thể do constant pool/layout; hãy kiểm tra attribute semantics, verifier và hành vi. |
| Chương trình sử dụng `java.lang.classfile` không biên dịch trên JDK 17 | API chuẩn chỉ có từ JDK 24; dùng JDK 24+ và không bật preview cho bản chuẩn. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Một transformer muốn thêm logging vào đầu method nhưng vẫn giữ khả năng debug. Chỉ giữ nguyên bytes của `LineNumberTable` từ class cũ có đủ không?

**Đáp án:** Không. Phải giữ/cập nhật các line entries theo vị trí mã mới; thao tác thêm bytecode có thể đổi offset. Nên làm việc qua `CodeModel` và kiểm tra breakpoint/line mapping sau transform.

**Câu 2.** Trong ví dụ, vì sao `unknownFixture` có `source=false` dù vẫn có line numbers?

**Đáp án:** Fixture đổi tên chính **class-level `SourceFile`** thành `MysteryTag` trên bản sao bytes, còn các attribute debug trong `Code` không bị sửa. `SourceFile` và `LineNumberTable` là hai loại riêng.

**Câu 3.** Bật `DROP_DEBUG` có tự động loại `RuntimeVisibleAnnotations` và `MethodParameters` không?

**Đáp án:** Không. Những attribute đó có ý nghĩa khác và được mô hình hóa riêng. Ví dụ `dropDebug` vẫn giữ cả annotation và method parameter metadata.

**Câu 4.** Một unknown attribute chứa offset bytecode, còn transform thêm lệnh vào giữa method. `PASS_ALL_ATTRIBUTES` có tự điều chỉnh offset bên trong unknown payload không?

**Đáp án:** Không. Vì payload chưa biết cấu trúc, API không có đủ thông tin sửa offset. Cần custom mapper hiểu format, hoặc không giữ attribute nếu không thể bảo đảm đúng.

**Câu 5.** Khi xây lại toàn bộ class với `ClassTransform.ACCEPT_ALL`, có thể khẳng định output luôn từng byte bằng input không?

**Đáp án:** Không. Hợp đồng tập trung vào mô hình class và semantics; có thể có tối ưu bulk-copy hoặc tái biểu diễn cấu trúc. Kiểm tra mô hình và hành vi thay vì bắt buộc checksum file phải giống.

**Câu 6.** Tại sao muốn xóa pseudo debug bằng option cần chú ý transform đã đi vào `CodeModel` chưa?

**Đáp án:** Nếu code được sao chép nguyên khối vì không đổi, thư viện có thể giữ các bytes attribute cũ. Khi xử lý method body qua `CodeTransform`, các option `DROP_*` mới quyết định các debug pseudo-instruction có được đưa qua builder hay không.

**Câu 7.** Nếu một công cụ khác ghi attribute riêng và bạn muốn bảo tồn qua đổi constant pool, nên bắt đầu từ đâu?

**Đáp án:** Tài liệu định dạng của attribute đó, xác định dependency vào constant pool/labels/offset, rồi xây custom `AttributeMapper` phù hợp hoặc thống nhất chính sách loại bỏ nếu không thể tái tạo đúng.

## 13. Tóm tắt và tài liệu đối chiếu

**Điều cần nhớ khi dùng Class-File API để instrument:**

1. Giữ **debug metadata** khi cần qua `PASS_DEBUG` và `PASS_LINE_NUMBERS`, đồng thời đảm bảo đã xử lý đúng `CodeModel`; debug line/local variables có thể cần remap khi lệnh di chuyển.
2. Giữ **thuộc tính chuẩn** còn đúng bằng việc pass-through model elements và để mapper/builder xử lý constant pool/labels; không loại annotation, generic signature, metadata runtime hay stack maps chỉ vì chúng không phải opcode.
3. Với **thuộc tính không nhận diện**, `PASS_ALL_ATTRIBUTES` cố giữ payload, còn `DROP_UNKNOWN_ATTRIBUTES`/`DROP_UNSTABLE_ATTRIBUTES` lựa chọn bỏ nhóm có dependency không an toàn. Giữ bytes **không đồng nghĩa** giữ được ý nghĩa sau mọi transform.
4. Khi biết format custom attribute, dùng `AttributeMapperOption` và mapper có hiểu dependency thay vì “sao chép mù”.
5. Luôn kiểm tra **class structure, verification và hành vi debugger/framework** trên output, đặc biệt với instrumentation đổi bytecode.

**Nguồn chính thức (Java 24/25 và JVMS):**

- [JEP 484 — Class-File API, chuẩn hóa ở JDK 24](https://openjdk.org/jeps/484)
- [Java 24 API — ClassFile và các options](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java 25 API — Class-File API package guide: reading, attributes, transforms](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html)
- [Java 25 API — AttributesProcessingOption: PASS_ALL / DROP_UNKNOWN / DROP_UNSTABLE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.AttributesProcessingOption.html)
- [Java 25 API — ClassTransform.ACCEPT_ALL và ClassTransform.transformingMethodBodies](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [Java 24 API — UnknownAttribute](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/attribute/UnknownAttribute.html)
- [JVMS §4.7 — Attributes](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html#jvms-4.7)