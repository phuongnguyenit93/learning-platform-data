# Quy tắc đặt tên, package và các phần tử nguồn gốc khi annotation processor sinh mã Java

## 1. Vì sao processor phải quản lý tên, package và nguồn gốc?

Trong Java, **annotation processor** chạy trong giai đoạn biên dịch và có thể kiểm tra khai báo, tạo chẩn đoán, sinh tệp nguồn Java, class file hoặc resource. Khi processor dùng API `javax.annotation.processing.Filer` để sinh mã, ba thông tin sau quyết định kết quả:

1. **Tên tệp/kiểu được sinh**: phải có quy tắc xác định, hợp lệ theo Java, không trùng với những kiểu hoặc tệp đã tồn tại trong cùng quá trình xử lý.
2. **Package đích**: kiểu được sinh thuộc package nào? Tên fully qualified truyền cho `Filer` phải khớp với câu lệnh `package` và tên class trong nội dung nguồn.
3. **Originating elements (các phần tử nguồn gốc)**: `Element` nào trong mô hình chương trình đầu vào là nguyên nhân khiến processor sinh ra file đó? Thông tin này giúp công cụ build xác định mối quan hệ giữa input và generated output.

Chẳng hạn, một class nguồn:

```java
package demo.model;

@GenerateGreeting
public class AccountConfig {}
```

có thể khiến processor sinh kiểu:

```java
package demo.model;

public final class AccountConfigGreeting {
    public static String message() {
        return "Generated for demo.model.AccountConfig";
    }
}
```

Hai đoạn trên là **minh họa**; muốn biên dịch phải có annotation `GenerateGreeting` cùng processor phù hợp. Với ví dụ này, tên kiểu được sinh là `demo.model.AccountConfigGreeting`, nằm trong package `demo.model`; phần tử nguồn gốc chính là `TypeElement` biểu diễn `demo.model.AccountConfig`.

**Nguyên tắc:** Một file sinh ra phải có tên đích xác định, nội dung Java phù hợp với tên đó và quan hệ nguồn gốc được khai báo trung thực. `Filer` chỉ đảm nhận phần tạo file theo cơ chế compiler; nó không tự thiết kế tên class, package hay chính sách tránh trùng cho ứng dụng.

## 2. Các khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Simple name | Tên kiểu không kèm package | `AccountConfigGreeting` |
| Package name | Tên package Java, không phải đường dẫn file nhập thủ công | `demo.model` |
| Fully qualified type name | Tên kiểu có package; dùng khi tạo Java source file | `demo.model.AccountConfigGreeting` |
| Generated source | Tệp `.java` mà processor tạo | `generated-src/demo/model/AccountConfigGreeting.java` |
| Generated class file | Bytecode do compiler tạo sau khi biên dịch nguồn sinh | `out/demo/model/AccountConfigGreeting.class` |
| Originating element | Một `javax.lang.model.element.Element` đầu vào góp phần hình thành output | `TypeElement` của `AccountConfig` |
| Output location | Vị trí output do compiler/file manager quản lý | `SOURCE_OUTPUT` hoặc `CLASS_OUTPUT` |

Trong Java, **package** được biểu diễn bằng tên có dấu chấm; đường dẫn dùng các thư mục tương ứng là việc `Filer` và file manager xử lý. Đừng truyền chuỗi đường dẫn `demo/model/AccountConfigGreeting.java` cho API `createSourceFile` rồi xem đó là fully qualified Java type name.

Phân biệt `Element` và `TypeMirror`:

- `Element` mô tả một **khai báo**: class, interface, field, method, parameter, package, module...
- `TypeMirror` mô tả **kiểu Java tại một vị trí**: declared type, array, primitive, type variable, wildcard...
- Tham số `originatingElements` của `Filer` là **`Element...`**, không phải `Class<?>` của reflection và không phải mảng `TypeMirror`. Với class được gắn annotation, thông thường hãy truyền chính `TypeElement` đó.

## 3. Đặt tên nguồn sinh với Filer.createSourceFile

Chữ ký API chính:

```java
JavaFileObject createSourceFile(
        CharSequence name,
        Element... originatingElements
) throws IOException;
```

Mã trên là **chữ ký API rút gọn**, không phải một phương thức bạn tự khai báo trong processor.

Tham số `name` biểu diễn tên **canonical/fully qualified của một type** muốn tạo (theo hợp đồng Java `Filer`); ví dụ:

```java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile("demo.model.AccountConfigGreeting", sourceElement);
```

`sourceElement` là một `Element` có thật trong mô hình compiler, giả sử đã được lấy trong logic processor. `Filer` tạo file ở source output location của compiler; nếu dùng `javac -s generated-src`, kết quả thông thường là `generated-src/demo/model/AccountConfigGreeting.java`.

Nội dung ghi vào file phải nhất quán với tên đích:

```java
package demo.model;

public final class AccountConfigGreeting {
}
```

Nếu `Filer` được yêu cầu tạo `demo.model.AccountConfigGreeting` mà nội dung lại khai báo `package demo.other;` hoặc tên public class khác, compiler sẽ không có một Java source file phù hợp và quá trình build có thể thất bại. `Filer` **không tự sửa** dòng `package` hoặc tên class theo nội dung bạn ghi.

### 3.1. Tạo tên từ mô hình chương trình, không cắt chuỗi đường dẫn

Với một `TypeElement source`:

```java
String packageName = processingEnv.getElementUtils()
        .getPackageOf(source).getQualifiedName().toString();

String generatedSimple = source.getSimpleName() + "Greeting";
String generatedName = packageName + "." + generatedSimple;
```

Đây là đoạn minh họa giả sử `source` đã được lấy từ processor và ví dụ **chỉ cho phép named package**. Nó phù hợp với `demo.model.AccountConfig`:

- `getPackageOf(source)` lấy `PackageElement` của nguồn, không dựa vào cấu trúc folder tự suy đoán.
- `getQualifiedName()` trên `PackageElement` trả tên package chuẩn.
- `getSimpleName()` trên `TypeElement` trả simple name của khai báo.
- `generatedName` trở thành `demo.model.AccountConfigGreeting`.

Dùng mô hình compiler thay vì tự lấy đường dẫn nguồn bằng `String.substring`, vì cây thư mục có thể chịu ảnh hưởng của generated sources, source roots, IDE, module layout hoặc bước build.

### 3.2. Quy tắc hợp lệ của Java identifier

Một tên kiểu/package trong Java không thể là tên tùy ý từ cấu hình:

- Simple name phải là **Java identifier hợp lệ** và không phải keyword theo mức ngôn ngữ áp dụng.
- Mỗi thành phần của package, ví dụ `demo` và `model`, phải hợp lệ trong ngữ cảnh tên package.
- Tên tạo ra không được trùng với tên kiểu đã có cùng package; Java không cho hai top-level type có cùng qualified name trong cùng chương trình.
- Java identifier không đồng nghĩa mẫu ASCII `[A-Za-z_][A-Za-z0-9_]*`; Java cho phép những ký tự Unicode khác theo quy tắc ngôn ngữ. Không nên dùng regex ASCII đơn giản để tuyên bố mọi identifier ngoài ASCII là sai.
- Đặc biệt với tên nhận từ tùy chọn người dùng hoặc annotation element, hãy **kiểm tra giá trị** thay vì chèn thẳng thành tên class.

`javax.lang.model.SourceVersion` có các trợ giúp như `isIdentifier(...)` và `isKeyword(...)`; hãy xét phiên bản source level mà processor thực sự hỗ trợ. Dựa trên tên khai báo đã hợp lệ từ compiler model và nối một hậu tố cố định (ví dụ `Greeting`) thường đơn giản và an toàn hơn nhiều so với cho phép tùy ý nhập tên file.

### 3.3. Default package và named package

`PackageElement.getQualifiedName()` của **unnamed package** có thể là chuỗi rỗng. Lúc đó, tên `packageName + "." + generatedSimple` sẽ bắt đầu bằng dấu chấm và không hợp lệ.

Có hai cách xử lý hợp lệ về mặt thiết kế:

1. **Chủ động không hỗ trợ unnamed package** và phát thông báo lỗi rõ ràng; đây là chính sách của ví dụ chạy được bên dưới.
2. Nếu ứng dụng thực sự hỗ trợ default package, tạo tên chỉ bằng simple name, không ghi dòng `package ...;` và cân nhắc giới hạn của unnamed package.

Không thể lấy tên package rỗng rồi luôn ghép thêm dấu chấm. Với thư viện cần dùng lại, nên ưu tiên **named package** để tránh đụng tên và quản lý API rõ ràng.

## 4. Package của mã được sinh: cùng package hay package riêng?

Hai chiến lược thường gặp:

**Sinh trong cùng package với class gốc:**

- `demo.model.AccountConfig` → `demo.model.AccountConfigGreeting`.
- Dễ theo dõi quan hệ tên; code sinh có thể truy cập các package-private declarations trong cùng package nếu những quy tắc Java/module liên quan cho phép.
- Cần quản lý va chạm tên trong từng package và tránh tạo class trùng với source người dùng.

**Sinh vào package chuyên biệt:**

- `demo.model.AccountConfig` → `demo.generated.AccountConfigGreeting`.
- Dễ gom mã sinh và phân biệt API được tạo với model gốc.
- Cần xử lý tình huống nhiều class khác package có cùng simple name; chỉ hậu tố `Greeting` có thể chưa đủ làm tên duy nhất. Có thể đưa thông tin qualified name vào chiến lược đặt tên, dùng cấu trúc subpackage hoặc phát lỗi collision.
- Package riêng làm thay đổi quyền truy cập các member package-private; không nên giả định generated code có cùng quyền như class gốc.

**Chọn chiến lược trước khi sinh:** một quy tắc chỉ dựa trên simple name sẽ gặp rủi ro khi có `alpha.User` và `beta.User` cùng sinh vào `demo.generated.UserGreeting`. Hãy thiết kế hàm tạo tên nhất quán cho toàn bộ project, không chọn tùy hứng theo thứ tự processor quét được các phần tử.

Với JPMS (Java Platform Module System), còn phải xét named module, quan hệ `requires`, `exports` và cách compiler tổ chức source output của module. Package name trong mã nguồn không tự quyết định module nào được phép đọc generated type. Ví dụ đầy đủ dưới đây dùng **classpath** để giữ trọng tâm vào `Filer`; không tự động áp dụng nguyên lệnh build ấy cho dự án `module-info.java` mà không điều chỉnh processor/module configuration.

## 5. Originating elements là gì?

Khi tạo tệp, `Filer` cho phép truyền không hoặc nhiều `Element` nguồn gốc:

```java
processingEnv.getFiler().createSourceFile(
        generatedName,
        annotatedType
);
```

Trong đó `annotatedType` là `TypeElement` của nguồn đã khiến processor tạo `generatedName`.

Với một output tổng hợp từ **nhiều khai báo**, có thể truyền nhiều phần tử nguồn gốc:

```java
processingEnv.getFiler().createSourceFile(
        "demo.generated.CombinedIndex",
        customerType,
        invoiceType
);
```

Đây là minh họa API; các biến `customerType` và `invoiceType` được giả định là `Element` hợp lệ trong processor.

### Tại sao originatingElements quan trọng?

- **Truy vết phụ thuộc:** build tool có thể ghi nhận “generated file này phụ thuộc vào khai báo nguồn nào”.
- **Hỗ trợ incremental processing/builds:** một số hệ thống build dùng thông tin nguồn gốc để quyết định generated outputs cần tái tạo khi input thay đổi.
- **Mô tả quan hệ thực:** output dựa vào một class thì truyền class đó; output tổng hợp nhiều class thì phải cân nhắc toàn bộ nguồn dữ liệu thực sự tham gia, không chỉ truyền một phần tử cho có.

**Giới hạn quan trọng:**

1. `originatingElements` chỉ là **thông tin gợi ý cho môi trường sinh mã và công cụ build**; Java compiler API không đảm bảo mọi build tool sẽ tự thực hiện incremental compilation tối ưu dựa vào tham số này.
2. **Không phải một annotation đặc biệt** được gắn vào generated class, không phải danh sách tham chiếu `Class<?>` ở runtime và không phải phần tử của Java source syntax.
3. **Không thay thế** việc xác định dependency bằng build system, việc quản lý generated sources, hay việc thiết kế processor theo yêu cầu incremental của từng công cụ.
4. Có thể bỏ qua varargs này theo API, nhưng một processor muốn xây dựng khả năng incremental rõ ràng thường nên truyền các `Element` thực sự gây ra output.
5. Với output tổng hợp từ **toàn bộ tập nguồn** hoặc dữ liệu ngoài compiler model, chỉ truyền một `TypeElement` tùy tiện có thể mô tả dependency sai. Cần tuân thủ contract của công cụ incremental thực tế; có tình huống processor nên được coi là **aggregating** thay vì **isolating**.
6. Processor có thể sinh file từ một `Element` nguồn `@Retention(SOURCE)`; retention của annotation kích hoạt **không làm mất** khả năng truyền `Element` nguồn gốc tại compile time.

Trong ví dụ `AccountConfig` → `AccountConfigGreeting`, đây là quan hệ **một input khai báo → một output source file**; truyền `TypeElement` của `AccountConfig` là cách ghi nguồn gốc trực tiếp và hợp lý.

## 6. Ví dụ Java 17+ hoàn chỉnh: dùng Filer để tạo source đúng tên, package và origin

Ví dụ này dùng annotation `@GenerateGreeting` có retention `SOURCE`. Processor đọc annotation trên **top-level class trong named package**, lấy package và simple name bằng compiler model, tạo class mới cùng package với hậu tố `Greeting` và truyền `TypeElement` nguồn vào `createSourceFile`.

### 6.1. Cấu trúc thư mục ban đầu

Tạo các tệp như sau:

```text
src/
├── demo/
│   ├── annotations/
│   │   └── GenerateGreeting.java
│   ├── model/
│   │   └── AccountConfig.java
│   └── app/
│       └── Main.java
└── tools/
    └── GreetingProcessor.java
```

Đây là ví dụ **classpath** dùng một project đơn giản, không có `module-info.java`.

### Tệp 1 — `src/demo/annotations/GenerateGreeting.java`

```java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {}
```

`SOURCE` là đủ vì processor cần đọc annotation khi biên dịch. `@Target(TYPE)` cho phép gắn vào các khai báo type; processor sẽ **tự thu hẹp** xuống top-level class.

### Tệp 2 — `src/tools/GreetingProcessor.java`

```java
package tools;

import demo.annotations.GenerateGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private final Set<String> created = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || element.getEnclosingElement().getKind()
                            != ElementKind.PACKAGE) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Only top-level classes are supported", element);
                continue;
            }

            TypeElement source = (TypeElement) element;
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(source).getQualifiedName().toString();

            if (packageName.isEmpty()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "A named package is required", source);
                continue;
            }

            String simpleName = source.getSimpleName() + "Greeting";
            String fullName = packageName + "." + simpleName;

            if (!created.add(fullName)) {
                continue;
            }

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(fullName, source);
                try (Writer writer = file.openWriter()) {
                    writer.write("package " + packageName + ";\n\n");
                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("    private " + simpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Generated for "
                            + source.getQualifiedName() + "\";\n");
                    writer.write("    }\n}\n");
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + fullName + ": "
                                + error.getMessage(),
                        source);
            }
        }
        return true;
    }
}
```

**Ý nghĩa những dòng quan trọng:**

- `@SupportedAnnotationTypes` chỉ ra annotation type mà processor công bố xử lý. `@SupportedSourceVersion(RELEASE_17)` nêu phiên bản ngôn ngữ được hỗ trợ.
- `getElementsAnnotatedWith(GenerateGreeting.class)` lấy các `Element` được đánh dấu trong vòng biên dịch hiện tại.
- `getKind() == ElementKind.CLASS` và `getEnclosingElement().getKind() == PACKAGE` giới hạn ví dụ ở **top-level class**. Đây là **quy định của demo**, không phải giới hạn bắt buộc của mọi annotation processor.
- `getPackageOf(source)` lấy package chuẩn từ compiler model, không phải từ đường dẫn chuỗi.
- `source.getSimpleName() + "Greeting"` tạo tên duy nhất **trong ví dụ**. Processor không thể bảo đảm không đụng tên chỉ bằng việc nối hậu tố, vì dự án khác có thể đã khai báo class cùng tên.
- `created` giữ tên đã thử tạo trong processor instance để tránh tạo lại chính tên đó ở vòng xử lý kế tiếp; nó **không** thay thế xử lý va chạm với input/user source hoặc processor khác.
- `createSourceFile(fullName, source)` tạo Java file theo fully qualified name và báo rằng **`source` là originating element**.
- Khối `try (Writer writer = ...)` đóng writer sau khi hoàn tất. Compiler có thể tiếp tục xử lý và biên dịch tệp sinh ra trong các round phù hợp.
- `IOException` được chuyển thành compiler diagnostic gắn với `source` thay vì in stack trace rồi coi build thành công.
- `return true` cho biết processor đã **claim những annotation types phù hợp** trong round, theo contract của `Processor`; nó không bảo đảm không có processor khác được kích hoạt bởi những điều kiện riêng.

Trong demo, literal chuỗi sinh ra chứa **qualified name lấy từ compiler model**, không có dữ liệu người dùng tự do. Nếu sinh Java string từ annotation element chứa dấu nháy, ký tự điều khiển hoặc dấu gạch chéo ngược, cần **escape literal đúng chuẩn Java**; không chèn thẳng raw text vào string literal rồi giả định nó luôn biên dịch.

### Tệp 3 — `src/demo/model/AccountConfig.java`

```java
package demo.model;

import demo.annotations.GenerateGreeting;

@GenerateGreeting
public class AccountConfig {}
```

Đây là **element nguồn gốc** của generated class. Processor đọc nó tại compile time dù `@GenerateGreeting` có `Retention(SOURCE)`.

### Tệp 4 — `src/demo/app/Main.java`

```java
package demo.app;

import demo.model.AccountConfigGreeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(AccountConfigGreeting.message());
    }
}
```

`Main` sử dụng class **chưa có trong thư mục `src` lúc bắt đầu biên dịch**, nhưng processor sẽ tạo nguồn của nó trong lượt `javac` thứ hai.

### 6.2. Biên dịch processor trước, rồi kích hoạt processor

Ở thư mục chứa `src`, nếu dùng Bash:

```bash
mkdir -p processor-out generated-src out
javac --release 17 -d processor-out src/demo/annotations/GenerateGreeting.java src/tools/GreetingProcessor.java
javac --release 17 -cp processor-out -processorpath processor-out -processor tools.GreetingProcessor -s generated-src -d out src/demo/model/AccountConfig.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Với Windows PowerShell, thay dòng tạo thư mục đầu tiên bằng:

```powershell
New-Item -ItemType Directory -Force processor-out, generated-src, out | Out-Null
```

Sau đó chạy ba lệnh `javac`, `javac`, `java` tương ứng trong PowerShell.

**Stdout chính xác của lệnh `java` cuối:**

```text
Generated for demo.model.AccountConfig
```

Ví dụ đã được biên dịch bằng `javac --release 17` trên JDK tương thích Java 17 và thực thi thành công. Các lệnh biên dịch không in dòng chẩn đoán nào trong trường hợp hợp lệ của ví dụ.

### 6.3. Tệp được sinh và được biên dịch

Sau lượt `javac` có processor, file sinh ra nằm dưới `-s generated-src`:

```text
generated-src/
└── demo/
    └── model/
        └── AccountConfigGreeting.java
```

Nội dung được sinh trong ví dụ:

```java
package demo.model;

public final class AccountConfigGreeting {
    private AccountConfigGreeting() {}
    public static String message() {
        return "Generated for demo.model.AccountConfig";
    }
}
```

Bên dưới `out` có bytecode `demo/model/AccountConfigGreeting.class` và `demo/app/Main.class` cùng các class cần thiết từ lượt biên dịch thứ hai. Lượt này có thể biên dịch code tham chiếu đến generated class vì processor đã tạo source ở đúng round/compiler-managed output.

Lựa chọn `-s` và `-d` là rất quan trọng:

- `-s generated-src`: chỉ ra nơi compiler ghi **generated Java source files**.
- `-d out`: chỉ ra nơi compiler ghi **compiled class files**.
- `-processorpath processor-out`: nơi compiler tìm và tải **annotation processor**.
- `-processor tools.GreetingProcessor`: chọn processor tường minh, không phụ thuộc auto-discovery/`META-INF/services`.
- `-cp processor-out`: cung cấp annotation type `GenerateGreeting` cho lượt biên dịch source ứng dụng.
- `--release 17`: chọn language/API target Java 17.

Đừng chạy `java -cp generated-src demo.app.Main`; `generated-src` chứa Java source của generated type, **không** phải thư mục bytecode để chạy. Trong demo, class thực thi ở `out`.

## 7. Vì sao phải xử lý rounds và tên sinh trùng?

Annotation processing có thể chạy theo **nhiều round**:

```text
Round 1: compiler đưa AccountConfig vào mô hình
         └── @GenerateGreeting kích hoạt GreetingProcessor
             └── tạo AccountConfigGreeting.java qua Filer
Round 2: compiler đưa generated source vào xử lý/biên dịch
         └── có thể phát hiện thêm annotation từ generated sources
Final round: roundEnv.processingOver() == true
         └── không tạo thêm nguồn trong demo
```

Đây là sơ đồ tổng quan; số lần round thực tế phụ thuộc input và công việc mà processor khác thực hiện.

Điều quan trọng:

1. Processor không nên **mỗi round lại tạo cùng qualified name**. `Filer` có cơ chế chống tái tạo cùng tên trong cùng processing run và có thể ném `FilerException` (là một dạng `IOException`).
2. `Set<String> created` trong ví dụ giảm nguy cơ tạo lại một tên do logic processor. Tuy nhiên nó **không** làm cho tên sinh an toàn trước tên type người dùng đã có hoặc processor khác đang tạo.
3. Nếu cùng một generated name được yêu cầu từ **hai source elements khác nhau**, không được lặng lẽ chọn cái được duyệt trước rồi bỏ cái còn lại; trong processor sản phẩm cần báo rõ collision, hoặc dùng chiến lược đặt tên bảo đảm phân biệt.
4. Không ghi trực tiếp file qua `FileWriter` vào thư mục build để lách `Filer`. Làm vậy có thể phá quản lý output của compiler, provenance, trình tự round và cách build tool theo dõi tệp sinh.
5. Khi sinh **nhiều file theo từng element**, có thể tạo tất cả những file có tên khác nhau trong một round. Khi sinh **file tổng hợp**, nên xác định lúc nào tập input đã đủ và cách xử lý nguồn gốc/tính tăng dần sao cho không phát một tên nhiều lần.

### FilerException không phải lỗi ngẫu nhiên

Một số tình huống dễ gây lỗi:

- Processor gọi `createSourceFile("demo.model.AccountConfigGreeting", ...)` hai lần trong cùng processing run.
- Tên được sinh trùng với một source/class file đang được compiler coi là input hoặc output trong lượt đang xử lý.
- Hai processor tạo cùng một qualified name.
- Một processor tính cùng một tên đích cho hai annotated classes mà không phát hiện trùng.

`FilerException` là tín hiệu cần kiểm tra lại **định danh output và quy tắc sinh mã**, không phải lý do để xóa file hoặc tiếp tục ghi đè bừa bãi. Trường hợp quyền ghi file, đường dẫn output hoặc I/O lỗi cũng có thể sinh `IOException` khác.

## 8. createSourceFile, createClassFile và createResource khác nhau thế nào?

`Filer` cung cấp các nhóm API tương ứng với loại output:

| API | Mục đích | Tên/đích |
| --- | --- | --- |
| `createSourceFile(name, origins...)` | Tạo file nguồn Java `.java` để compiler có thể xử lý tiếp | Tên kiểu Java đủ package, ví dụ `demo.model.AccountConfigGreeting` |
| `createClassFile(name, origins...)` | Tạo class file trực tiếp khi có bytecode hợp lệ | Tên kiểu Java tương ứng; không dùng để ghi text Java |
| `createResource(location, moduleAndPkg, relativeName, origins...)` | Tạo tài nguyên không phải Java source/class file | Output location, package/module-and-package khi thích hợp, tên file tương đối |

Ví dụ tạo một resource đi kèm với một source element:

```java
FileObject file = processingEnv.getFiler().createResource(
        StandardLocation.CLASS_OUTPUT,
        "demo.model",
        "metadata.txt",
        sourceType
);
try (Writer out = file.openWriter()) {
    out.write("generated for demo.model.AccountConfig");
}
```

Đây là mã minh họa **nằm trong processor**: cần import `javax.tools.FileObject`, `javax.tools.StandardLocation`, `java.io.Writer` và khai báo `sourceType`. Nó có thể tạo tài nguyên dưới khu vực class output theo package `demo.model`, không tạo kiểu Java mang tên `metadata`.

Quy tắc với resource:

- `relativeName` là tên tương đối hợp lệ, không phải đường dẫn tuyệt đối tùy ý hoặc chuỗi dùng `../` để thoát output location.
- `moduleAndPkg` trong môi trường hỗ trợ module có các quy tắc bổ sung về module/package; nếu build dùng JPMS, cần cấu hình module output phù hợp, không tự giả định một folder tùy ý là một Java package/module.
- `CLASS_OUTPUT` thường là nơi các resource đóng gói cùng compiled classes; `SOURCE_OUTPUT` dành cho generated source output tùy loại resource/công cụ.
- Hãy truyền originating elements phù hợp cho **cả generated source và resource** để mô tả đầu vào thực sự gây ra mỗi output.

`createClassFile` cần **bytecode đúng định dạng JVM class file**, không phải `writer.write("public class ...")`. Nếu bạn chỉ cần sinh Java source, hãy dùng `createSourceFile` và để `javac` biên dịch tiếp.

## 9. Originating elements so với @Generated và annotation trên generated type

Hai cơ chế thường bị đánh đồng:

**`originatingElements`**: được truyền cho `Filer` ở thời điểm tạo file. Nó mô tả mối quan hệ giữa generated output và khai báo nguồn trong **môi trường biên dịch/build**.

**`@Generated`**: trong môi trường Java 9+, annotation `javax.annotation.processing.Generated` có thể được ghi vào mã nguồn sinh như dấu hiệu “mã được tạo bởi công cụ”, ví dụ thông tin processor. Nó là **metadata của generated source**, không thay thế tham số originating elements và không tự cho build tool biết toàn bộ nguồn đầu vào đã dùng.

Ví dụ cú pháp minh họa:

```java
@javax.annotation.processing.Generated("tools.GreetingProcessor")
public final class ExampleGenerated {}
```

Đoạn trên minh họa cách đánh dấu một type được sinh; không phải là mã tạo file qua `Filer`. `@Generated` có retention `SOURCE` và không phải cơ chế runtime reflection để suy ra originating elements. Dù có `@Generated`, processor vẫn cần quyết định nguồn gốc chính xác cho `createSourceFile` nếu build tool dựa vào thông tin này.

Một processor có thể sinh metadata `@Generated` để giúp con người và công cụ đọc source phân biệt generated code với code viết tay, **đồng thời** truyền `originatingElements` để mô tả provenance cho build. Hai điều này bổ trợ, không thay thế nhau.

## 10. Quy tắc thiết kế processor ổn định

### 10.1. Đặt tên tất định

Với cùng bộ input, processor nên tính ra **cùng qualified output name** bất kể thứ tự duyệt element hoặc thứ tự round. Không nên lấy timestamp, random value, thứ tự phần tử trong một tập không bảo đảm hoặc trạng thái toàn cục tùy ý làm thành phần bắt buộc của generated Java type name.

Nếu tên phụ thuộc vào nhiều input, cần một quy tắc ổn định để ghép/định danh các input ấy. Khi xuất file tổng hợp, có thể dùng một tên cố định có kiểm soát như `demo.generated.Registry` nhưng phải giải quyết vấn đề collision và phối hợp với các processor khác.

### 10.2. Kiểm tra đầu vào trước khi mở Writer

Trước khi gọi `createSourceFile`:

1. Kiểm tra element thuộc loại được hỗ trợ (`ElementKind`, nesting, package).
2. Tính package và qualified name từ mô hình compiler, không từ đường dẫn tự dựng.
3. Kiểm tra tên hợp lệ và không tự biết đã xung đột trong tập input được processor kiểm soát.
4. Xác định các originating elements thực sự có liên quan.
5. Chỉ sau đó mới gọi `Filer` và mở writer; cuối cùng đóng writer bằng try-with-resources.

Không nên tạo nửa file rồi mới phát hiện dữ liệu không hợp lệ: output sinh dở có thể khiến compiler báo thêm lỗi khó hiểu.

### 10.3. Phát diagnostic đúng vị trí

Dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, message, element)` để báo lỗi tại khai báo nguồn liên quan. Người dùng project sẽ thấy chẩn đoán compiler gắn với element, dễ sửa hơn `System.out.println` hoặc stack trace.

`Diagnostic.Kind.WARNING` phù hợp vấn đề có thể tiếp tục; `ERROR` phù hợp trường hợp không thể sinh mã đúng. Khi ghi file sinh thất bại, không được lặng lẽ xem quá trình thành công.

### 10.4. Tính ổn định và incremental compilation

Nếu output phụ thuộc **chính xác một annotated element**, quan hệ một-một thường dễ theo dõi. Nếu output phụ thuộc **tất cả các annotated elements** (ví dụ một registry hợp nhất), cần xây dựng mô hình dependency/aggregation đúng với build tool. `Filer` cho phép khai báo originating elements nhưng **không tự biến mọi processor thành isolating/incremental processor**.

Ngoài ra, thay đổi annotation element, package name hoặc tên class nguồn có thể làm thay đổi generated qualified name. Build system cần dọn output cũ và xử lý dependency đúng; processor không nên tự viết logic xóa bừa bãi nhiều đường dẫn ngoài `Filer`.

### 10.5. Không mặc định sinh vào package trống

Thư viện nên quy định rõ có hỗ trợ unnamed package không. Nếu không hỗ trợ, tạo diagnostic như demo. Nếu có, phải tính tên và dòng `package` riêng cho trường hợp không có package.

### 10.6. Generated code vẫn phải tuân Java và JPMS

Java source được sinh là Java source bình thường. Nó chịu các quy tắc về tên public class và file, package, visibility, generic type, import, module accessibility và compiler flags. `Filer` không tự cấp quyền truy cập member private hoặc vượt `exports`/`requires`.

Tránh sinh mã bằng cách copy tên raw của class/field mà không xử lý keyword, ký tự đặc biệt, escaping và collision. Phân biệt lỗi do Filer đặt output với lỗi do Java source được tạo không hợp lệ.

## 11. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `FilerException: Attempt to recreate a file` | Cùng tên được tạo nhiều lần trong processing run hoặc va chạm với file được compiler quản lý | Đặt tên tất định, chặn duplicate và kiểm tra collision; không ghi đè |
| Java compiler báo package/type mismatch | `createSourceFile` nhận tên `a.b.X` nhưng source ghi `package c.d;` hoặc public class khác `X` | Sinh `package a.b;` và khai báo `X` đúng |
| Tên có dấu chấm đầu như `.AccountGreeting` | Ghép package rỗng với `"."` vô điều kiện | Xử lý unnamed package riêng hoặc báo không hỗ trợ |
| Hai class khác package sinh cùng một output | Dùng simple name mà bỏ thông tin package/nguồn | Đặt tên đủ phân biệt; phát diagnostic nếu trùng |
| Processor chạy nhưng không sinh mã | Processor chưa được đăng ký/kích hoạt, unsupported annotation type hoặc không có annotated element phù hợp | Dùng `-processor`, `-processorpath`, kiểm tra supported types và rounds |
| Generated class không được tìm thấy | Tên package, tên class, source output hoặc compilation command sai | Kiểm tra `-s`, `-d`, generated qualified name và lỗi compiler |
| Sinh file một phần, build lỗi lạ | Không đóng writer hoặc lỗi I/O trong lúc ghi | Try-with-resources, xử lý `IOException` thành diagnostic |
| Truyền một originating element tùy ý cho file tổng hợp | Provenance không khớp input thực tế | Ghi nhận các nguồn góp phần, chọn mô hình incremental phù hợp |
| Cho rằng `@Generated` thay originatingElements | Hai cơ chế độc lập | Gắn `@Generated` nếu muốn; vẫn truyền origins cho Filer |
| Viết trực tiếp Java vào `createClassFile` | API này dành cho binary class file | Dùng `createSourceFile` để sinh source Java |
| Dựa vào file system path là package | Source roots/module layout và package model khác chuỗi path | Dùng `Elements.getPackageOf` |
| Sinh Java literal từ chuỗi không escape | Ký tự `"`, `\`, xuống dòng làm source hỏng | Escape theo Java source syntax hoặc dùng thư viện JavaPoet tương thích |

## 12. Tự kiểm chứng với ví dụ hoàn chỉnh

Bạn có thể làm các thử nghiệm nhỏ sau (mỗi thử nghiệm sửa fixture rồi biên dịch lại, không phải các thay đổi đồng thời):

**Thử nghiệm A — đổi package nguồn.** Chuyển `AccountConfig` sang `demo.domain`, cập nhật đường dẫn/tuyên bố package và phần phụ thuộc `Main`. Nếu processor lấy package đúng từ compiler model, generated source phải nằm trong package `demo.domain`. Nếu mã sinh vẫn nằm `demo.model`, nghĩa là processor đã hard-code package.

**Thử nghiệm B — đổi tên class nguồn.** Đổi `AccountConfig` thành `UserConfig` cùng với tên file đầu vào. Generated name phải đổi thành `demo.model.UserConfigGreeting` theo quy tắc hậu tố. Nhớ xóa/đặt lại thư mục output trong môi trường kiểm thử khi cần để tránh nhầm class file cũ với output mới.

**Thử nghiệm C — dùng unnamed package.** Gắn `@GenerateGreeting` vào một top-level class không có `package`. Processor demo sẽ phát thông báo `A named package is required`. Đây là **hành vi thiết kế của ví dụ**, không chứng minh Filer luôn cấm unnamed package.

**Thử nghiệm D — nested class.** Gắn `@GenerateGreeting` lên một nested class. Processor demo báo `Only top-level classes are supported`. Nếu dự án cần hỗ trợ nested classes, phải tính tên sinh tránh trùng từ `getQualifiedName`/enclosing chain và xem xét vị trí generated type.

**Thử nghiệm E — trùng tên.** Thêm một source `demo.model.AccountConfigGreeting` do người dùng viết tay, rồi thử biên dịch. Compiler/`Filer` có thể báo lỗi xung đột. Sửa bằng cách đổi naming strategy hoặc phát lỗi rõ ràng; **không** xóa source người dùng.

**Thử nghiệm F — SOURCE retention.** Giữ `@GenerateGreeting` là `SOURCE`. Chạy `javap -v -classpath out demo.model.AccountConfig`: lần dùng annotation SOURCE không xuất hiện ở annotation attributes trên class nguồn, nhưng generated class `AccountConfigGreeting` vẫn được tạo vì processor đã xử lý ở compile time.

**Thử nghiệm G — origin từ nhiều class.** Nếu sinh một file `AllConfigs` dựa trên hai annotated classes, hãy truyền cả hai originating elements, kiểm tra build tool được dùng có hỗ trợ đúng mô hình dependency này hay cần processor được cấu hình aggregating. Không suy luận chỉ từ việc ví dụ Java cơ bản biên dịch thành công.

## 13. Checklist trước khi đưa processor vào dự án

- [ ] Xác định annotation dùng cho **kiểm tra/sinh mã ở compile time** và retention đúng (thường `SOURCE` nếu không cần metadata runtime).
- [ ] Xác định chính xác `ElementKind` nào processor hỗ trợ; xử lý riêng nested/top-level, package rỗng nếu cần.
- [ ] Tên generated type có quy tắc **hợp lệ, ổn định, duy nhất trong phạm vi build**.
- [ ] `createSourceFile` nhận **qualified type name**, không phải đường dẫn tự tạo; nội dung nguồn chứa package/class khớp tên đó.
- [ ] Processor truyền **originating elements thực** cho mỗi output khi có; không giả định `@Generated` thay thế.
- [ ] Processor kiểm tra collision, không tạo trùng qua nhiều rounds hoặc giữa các annotated elements.
- [ ] Writer được đóng, lỗi `IOException`/`FilerException` thành compiler diagnostic.
- [ ] Lệnh build cấu hình processor path, discovery/`-processor`, `-s`, `-d` minh bạch; generated source được compiler xử lý.
- [ ] Nếu dùng JPMS hoặc incremental build, đã kiểm tra các quy tắc phụ thuộc/package/module và metadata origins với công cụ build cụ thể.
- [ ] Có kiểm thử: source hợp lệ, package trống, class lồng nhau, collision, nhiều rounds, rename input và output cũ.

**Ghi nhớ:** `Filer.createSourceFile("pkg.Type", originatingElement)` tạo nguồn Java theo **tên kiểu đủ package**, còn nội dung phải khai báo đúng `package pkg;` và `Type`. `originatingElements` mô tả **những khai báo đầu vào dẫn đến file được sinh**, hữu ích cho build tools nhưng không tự bảo đảm incremental compilation. Đặt tên tất định, nhận package từ compiler model và quản lý collision/rounds chính là nền tảng để annotation processor sinh mã Java đáng tin cậy.
