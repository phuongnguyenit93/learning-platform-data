# Sinh nguồn và tài nguyên bằng Filer trong Java Annotation Processing

Khi xây dựng một annotation processor bằng API **JSR 269** (package `javax.annotation.processing`), nhu cầu phổ biến là đọc các khai báo có annotation rồi sinh **tệp nguồn Java** hoặc **tài nguyên** để trình biên dịch và ứng dụng sử dụng. API chuẩn dành cho việc đó là **`Filer`**, lấy qua `ProcessingEnvironment.getFiler()`.

Ví dụ một class `@GenerateCompanion Hello` được processor nhận diện và sinh `HelloCompanion.java`, đồng thời sinh tệp `META-INF/lesson/generated.txt` liệt kê tên class vừa tạo. `javac` có thể tiếp tục biên dịch mã nguồn mới ở processing round tiếp theo. Resource đi vào output để ứng dụng đọc khi chạy, không cần nhúng chuỗi cố định trong mã nguồn.

Điều quan trọng: `Filer` **tạo file mới có tên được quản lý bởi compiler**; nó không phải API sửa trực tiếp abstract syntax tree (AST) của class đang được biên dịch, cũng không phải cách viết đè source đầu vào.

## 1. Filer nằm ở đâu trong quá trình biên dịch?

Một processor chuẩn nhận đối tượng `ProcessingEnvironment` khi được khởi tạo. Từ môi trường đó, nó có thể sử dụng:

| API | Công dụng |
| --- | --- |
| `processingEnv.getFiler()` | Tạo source, class file hoặc resource mới |
| `processingEnv.getMessager()` | Phát `NOTE`, `WARNING`, `ERROR` cho compiler |
| `processingEnv.getElementUtils()` | Đọc package, tên khai báo và mô hình `Element` |
| `processingEnv.getTypeUtils()` | Phân tích/so sánh `TypeMirror` |
| `RoundEnvironment` | Biết phần tử có annotation và trạng thái processing round |

Sơ đồ ý tưởng:

~~~text
App.java (@GenerateCompanion)
             |
             v
      javac: parse/enter
             |
             v
  JSR 269 annotation processor
      |                 |
      | Filer           | Filer
      v                 v
HelloCompanion.java   META-INF/lesson/generated.txt
      |                 |
      v                 v
round sau của javac   CLASS_OUTPUT/resource
      |
      v
HelloCompanion.class
      |
      v
Chạy App -> gọi method sinh và đọc resource
~~~

Sơ đồ đơn giản hóa các pha nội bộ của `javac`. Điều phải nhớ là **source được sinh** có thể trở thành input cho round/pha biên dịch tiếp theo; còn **resource** thường được đóng cùng đầu ra lớp/JAR để ứng dụng sử dụng.

### Filer khác File/Files thế nào?

`java.io.File` và `java.nio.file.Files` là API I/O thông thường: chúng có thể viết một đường dẫn bất kỳ mà tiến trình có quyền. `Filer` có thêm **hợp đồng của annotation processing**: quản lý tên file, vị trí output, phát hiện cố tạo trùng và cho compiler biết về tệp mới được sinh.

Trong processor nên ưu tiên `Filer` cho file thuộc sản phẩm build. Nếu tự ghi `.java` bằng `Files.writeString(...)` vào một thư mục tùy ý, compiler **không tự động có nghĩa vụ phát hiện và biên dịch** tệp ấy trong cùng processing run.

## 2. Bốn thao tác chính của Filer

Interface `javax.annotation.processing.Filer` cung cấp bốn nhóm thao tác:

| Phương thức | Kết quả | Đối số quan trọng |
| --- | --- | --- |
| `createSourceFile(name, origins...)` | `JavaFileObject` chứa source của một type mới | Tên chuẩn đầy đủ của type, ví dụ `demo.HelloCompanion` |
| `createClassFile(name, origins...)` | `JavaFileObject` chứa dữ liệu class file | Binary name, nội dung bytecode **hợp lệ** |
| `createResource(location, pkg, relativeName, origins...)` | `FileObject` cho resource mới | Output location, package (có thể rỗng), đường dẫn tương đối |
| `getResource(location, pkg, relativeName)` | `FileObject` để đọc resource đã có trong vị trí thích hợp | Không tạo file mới; có quy tắc hạn chế đọc file do cùng processor tạo |

Dùng **`createSourceFile`** khi muốn compiler tự xử lý source Java được sinh. `createClassFile` dành cho công cụ thực sự tạo bytecode class file hợp lệ, ví dụ code generator sinh bytecode bằng thư viện chuyên dụng; ghi văn bản Java vào `createClassFile` sẽ không tạo được bytecode hợp lệ.

`createResource` không chỉ dành cho tệp `.properties`. Nó có thể tạo file `.txt`, metadata, index hoặc các resource khác. Trong bài học, ta chọn một đường dẫn `META-INF/...` rõ ràng.

### `originatingElements`

Các tham số cuối của `createSourceFile`, `createClassFile` và `createResource` là `Element... originatingElements`. Hãy truyền khai báo nguồn đã khiến processor sinh sản phẩm, ví dụ class `Hello` có `@GenerateCompanion`. Điều này **mô tả quan hệ nguồn → đầu ra**, hữu ích cho công cụ incremental build hoặc chẩn đoán.

Nó **không** sửa phạm vi/đường dẫn của file, không quyết định compiler sẽ compile thành công, và không thay thế logic quản lý vòng xử lý. Hỗ trợ incremental chính xác còn phụ thuộc build tool và hành vi processor.

## 3. Source output, class output và resource location

Một lỗi thường gặp là nhầm vị trí output.

| Công cụ/khái niệm | Vai trò |
| --- | --- |
| `-s build/generated` của `javac` | Nơi lưu các file `.java` được annotation processor sinh |
| `-d build/classes` | Nơi chứa các `.class` sau biên dịch và tài nguyên `CLASS_OUTPUT` |
| `StandardLocation.SOURCE_OUTPUT` | Vị trí output cho source được sinh và resource được tạo ở source output |
| `StandardLocation.CLASS_OUTPUT` | Vị trí class output; resource tạo tại đây có thể được đóng vào JAR cùng classes |
| `StandardLocation.CLASS_PATH` | Vị trí đọc/tìm classes hoặc resources thuộc classpath; **không phải output root mặc định để tạo resource** |
| `-processorpath ...` | Nơi `javac` tìm processor cần chạy |
| `-cp ...` | Nơi `javac` tìm các type mà mã ứng dụng cần khi biên dịch |

Với `createSourceFile("demo.HelloCompanion", ...)` và `-s build/generated`, compiler tạo đường dẫn tương ứng:

~~~text
build/generated/demo/HelloCompanion.java
~~~

Với:

~~~java
filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/lesson/generated.txt",
        origin
);
~~~

resource nằm tương ứng:

~~~text
build/classes/META-INF/lesson/generated.txt
~~~

Đoạn `createResource` là **minh họa bên trong processor**, với biến `filer` và `origin` có sẵn. Chuỗi `relativeName` là tên tương đối dùng dấu `/` theo ngữ nghĩa của `Filer`, không phải một đường dẫn tuyệt đối của Windows. Không dùng tên có đường đi lên như `../outside.txt` hoặc đường dẫn bắt đầu bằng `/` để cố thoát output root.

**Quyết định đặt resource ở đâu là quan trọng**: `CLASS_OUTPUT` thường thích hợp cho tài nguyên sẽ xuất hiện trên runtime classpath; `SOURCE_OUTPUT` thích hợp cho tài nguyên gắn với thư mục generated sources. Không trông đợi runtime tự đọc được resource chỉ ở `build/generated` khi chỉ thêm `build/classes` vào classpath.

## 4. Ví dụ Java 17 hoàn chỉnh: sinh class và một resource

Ví dụ sau dùng duy nhất JDK 17+, không cần Maven/Gradle hay thư viện ngoài. Ta tạo annotation `@GenerateCompanion`, processor `CompanionProcessor` và ứng dụng `Hello`. Processor sinh **`demo.app.HelloCompanion`** với method `message()`, đồng thời ghi đường dẫn class sinh ra vào resource.

Đặt các file như sau:

~~~text
filer-lab/
└── src/
    ├── api/demo/api/GenerateCompanion.java
    ├── processor/demo/processor/CompanionProcessor.java
    └── app/demo/app/Hello.java
~~~

Ba source root tách biệt giúp biên dịch processor trước, sau đó dùng processor khi compile ứng dụng.

### 4.1. Định nghĩa annotation

**Tệp `src/api/demo/api/GenerateCompanion.java`:**

~~~java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateCompanion {
}
~~~

- `TYPE` cho phép đặt annotation lên khai báo type theo quy tắc Java.
- `SOURCE` đủ để processor nhìn thấy annotation trong quá trình biên dịch; khi ứng dụng chạy, annotation **không cần** xuất hiện trong `Hello.class`.
- Annotation này **không tự sinh file**; phải có processor được chỉ định để đọc nó.

### 4.2. Processor dùng createSourceFile và createResource

**Tệp `src/processor/demo/processor/CompanionProcessor.java`:**

~~~java
package demo.processor;

import demo.api.GenerateCompanion;
import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.List;
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
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.api.GenerateCompanion")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class CompanionProcessor extends AbstractProcessor {
    private boolean resourceCreated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        List<String> generatedNames = new ArrayList<>();
        List<Element> origins = new ArrayList<>();

        for (Element element
                : roundEnv.getElementsAnnotatedWith(GenerateCompanion.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateCompanion requires a class",
                        element
                );
                continue;
            }

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(element)
                    .getQualifiedName()
                    .toString();
            String generated = element.getSimpleName() + "Companion";
            String qualified = pkg.isEmpty()
                    ? generated : pkg + "." + generated;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(qualified, element);
                try (Writer writer = source.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n");
                    }
                    writer.write("public final class " + generated + " {\n");
                    writer.write("  private " + generated + "() {}\n");
                    writer.write(
                            "  public static String message() {\n"
                            + "    return \"Generated for "
                            + element.getSimpleName()
                            + "\";\n"
                            + "  }\n"
                    );
                    writer.write("}\n");
                }
                generatedNames.add(qualified);
                origins.add(element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualified + ": "
                                + ex.getMessage(),
                        element
                );
            }
        }

        if (!generatedNames.isEmpty() && !resourceCreated) {
            try {
                FileObject resource = processingEnv.getFiler()
                        .createResource(
                                StandardLocation.CLASS_OUTPUT,
                                "",
                                "META-INF/lesson/generated.txt",
                                origins.toArray(new Element[0])
                        );
                try (Writer writer = resource.openWriter()) {
                    for (String name : generatedNames) {
                        writer.write(name + "\n");
                    }
                }
                resourceCreated = true;
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot write generated index: "
                                + ex.getMessage()
                );
            }
        }

        return true;
    }
}
~~~

Giải thích từng phần:

1. `@SupportedAnnotationTypes` khai báo tên đầy đủ của annotation mà processor nhận.
2. `@SupportedSourceVersion(RELEASE_17)` khai báo mức source processor hỗ trợ; các lệnh build bên dưới dùng `--release 17` để có cấu hình nhất quán.
3. `roundEnv.getElementsAnnotatedWith(GenerateCompanion.class)` tìm những khai báo đánh dấu annotation trong round hiện tại.
4. Processor chỉ sinh cho `ElementKind.CLASS`. Đây là chính sách riêng của lab; `@Target(TYPE)` còn có thể áp dụng cho những kiểu khai báo khác, nhưng processor báo lỗi nếu gặp chúng.
5. `getPackageOf(element)` xác định package. Tên output được tạo từ tên class gốc cộng `Companion`.
6. `createSourceFile(qualified, element)` tạo source mới, với `element` làm originating element.
7. `source.openWriter()` ghi văn bản Java, và `try-with-resources` đóng writer. Compiler chỉ có thể xử lý ổn định đầu ra sau khi file được đóng.
8. `createResource(CLASS_OUTPUT, "", "META-INF/lesson/generated.txt", ...)` tạo resource ở class output, không phải source output.
9. `resourceCreated` tránh cố ghi cùng một resource ở nhiều round. Nó là một cờ đơn giản đủ cho lab; processor production xử lý dữ liệu phát hiện ở round muộn cần chiến lược tổng hợp khác.
10. `return true` nghĩa là processor **claim** các annotation types đang được xử lý theo hợp đồng API. Nó không có nghĩa mọi thao tác I/O thành công.

**Giới hạn chủ đích của lab:** processor sinh resource index dựa trên các class annotated được phát hiện trong round có sản phẩm đầu tiên. Với một class `Hello`, output hoàn chỉnh và quyết định được. Nếu cần tổng hợp mọi class được nhiều processor khác sinh ở những round sau, cần thiết kế một **aggregating processor** có chiến lược thu thập element và ghi resource một lần ở thời điểm hợp lệ; không tự tái tạo cùng file ở mỗi round.

### 4.3. Ứng dụng dùng class và resource được sinh

**Tệp `src/app/demo/app/Hello.java`:**

~~~java
package demo.app;

import demo.api.GenerateCompanion;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

@GenerateCompanion
public final class Hello {
    public static void main(String[] args) throws Exception {
        System.out.println(HelloCompanion.message());

        try (InputStream stream = Hello.class.getClassLoader()
                .getResourceAsStream("META-INF/lesson/generated.txt")) {
            if (stream == null) {
                throw new IllegalStateException("Missing generated resource");
            }
            String index = new String(
                    stream.readAllBytes(),
                    StandardCharsets.UTF_8
            );
            System.out.print(index);
        }
    }
}
~~~

`HelloCompanion` **không tồn tại trong source đầu vào**; compile sẽ thành công khi processor sinh `HelloCompanion.java` rồi compiler biên dịch nó. Resource được đọc từ runtime classpath bằng `ClassLoader.getResourceAsStream`.

`readAllBytes()` có từ Java 9; bài lab đặt Java 17 nên không có vấn đề tương thích API. Resource chứa dấu xuống dòng cuối nên chương trình dùng `print` để không tự thêm một dòng trống.

### 4.4. Compile theo hai giai đoạn trên Linux/macOS (Bash)

Từ thư mục gốc `filer-lab`:

~~~bash
mkdir -p build/processor build/classes build/generated

javac --release 17 -encoding UTF-8 \
  -d build/processor \
  src/api/demo/api/GenerateCompanion.java \
  src/processor/demo/processor/CompanionProcessor.java

jar --create --file build/companion-processor.jar \
  -C build/processor .

javac --release 17 -encoding UTF-8 \
  -cp build/companion-processor.jar \
  -processorpath build/companion-processor.jar \
  -processor demo.processor.CompanionProcessor \
  -s build/generated \
  -d build/classes \
  src/app/demo/app/Hello.java

java -cp build/classes demo.app.Hello
~~~

**Stdout chính xác của ứng dụng:**

~~~text
Generated for Hello
demo.app.HelloCompanion
~~~

`javac` và `jar` thành công thông thường không cần in dòng output giải thích. Trong thí nghiệm, cấu trúc đầu ra quan trọng là:

~~~text
build/
├── companion-processor.jar
├── processor/
│   └── demo/
│       ├── api/GenerateCompanion.class
│       └── processor/CompanionProcessor.class
├── generated/
│   └── demo/app/HelloCompanion.java
└── classes/
    ├── demo/app/Hello.class
    ├── demo/app/HelloCompanion.class
    └── META-INF/lesson/generated.txt
~~~

**Tại sao compile đúng dù `Hello.java` gọi một class chưa có?** Ở round đầu, processor nhận ra `@GenerateCompanion` và tạo source `HelloCompanion.java`. Compiler tiếp tục xử lý source mới trước khi kết thúc lần biên dịch. `Hello.class` có thể tham chiếu `HelloCompanion.class` như một kiểu bình thường.

Nếu tắt processor trên một build **sạch**, compiler sẽ không tạo companion và báo `cannot find symbol` tại chỗ dùng `HelloCompanion`.

### 4.5. Windows PowerShell

Cũng từ root `filer-lab`, sau khi đã tạo ba file Java như trên:

~~~powershell
New-Item -ItemType Directory -Force "build\processor", "build\classes", "build\generated" | Out-Null

javac --release 17 -encoding UTF-8 -d "build\processor" "src\api\demo\api\GenerateCompanion.java" "src\processor\demo\processor\CompanionProcessor.java"

jar --create --file "build\companion-processor.jar" -C "build\processor" .

javac --release 17 -encoding UTF-8 -cp "build\companion-processor.jar" -processorpath "build\companion-processor.jar" -processor demo.processor.CompanionProcessor -s "build\generated" -d "build\classes" "src\app\demo\app\Hello.java"

java -cp "build\classes" demo.app.Hello
~~~

Stdout giống bản Bash:

~~~text
Generated for Hello
demo.app.HelloCompanion
~~~

Để đơn giản hóa, ta chỉ dùng **một** runtime classpath entry `build/classes`, nên không cần dấu nối entry `;` (Windows) hoặc `:` (Linux/macOS). Nếu sau này cần nhiều entry, dùng đúng dấu phân cách theo hệ điều hành.

### 4.6. Đóng gói generated source và resource vào JAR

Sau khi biên dịch ứng dụng, chạy:

~~~bash
jar --create --file build/app.jar -C build/classes .
jar --list --file build/app.jar
java -cp build/app.jar demo.app.Hello
~~~

Trong danh sách JAR cần có ít nhất:

~~~text
demo/app/Hello.class
demo/app/HelloCompanion.class
META-INF/lesson/generated.txt
~~~

Các dòng trên là **những entry cần xác nhận**, không phải toàn bộ stdout của `jar --list` (JAR còn có manifest và thư mục). Khi chạy `java -cp build/app.jar demo.app.Hello`, stdout vẫn là:

~~~text
Generated for Hello
demo.app.HelloCompanion
~~~

Vì `@GenerateCompanion` là annotation SOURCE retention, ứng dụng này không cần phải nạp annotation type hoặc processor lúc runtime; JAR ứng dụng đã chứa `Hello`, class generated và resource cần thiết.

## 5. Filer.createSourceFile: chọn tên đúng, nội dung đúng

Đối số `name` của `createSourceFile` là **tên type** theo cú pháp Java thích hợp, không phải đường dẫn file tùy ý. Ví dụ:

~~~java
JavaFileObject output = processingEnv.getFiler()
        .createSourceFile("com.acme.generated.UserMapper", origin);
~~~

Đoạn này là **mã bên trong processor**. Nếu `-s target/generated-sources`, file tương ứng là:

~~~text
target/generated-sources/com/acme/generated/UserMapper.java
~~~

Những nguyên tắc nên tuân thủ:

- Tính tên đầy đủ từ package + simple name của type mục tiêu. Không ghép đường dẫn hệ điều hành theo cách thủ công trong đối số.
- Sinh package declaration khớp tên đã yêu cầu: `package com.acme.generated;` cho class `UserMapper`.
- Với generated class kiểu public, tên file và tên class phải phù hợp quy tắc Java.
- Bảo đảm source sinh ra là Java hợp lệ. Để sinh chuỗi Java từ dữ liệu annotation cần **escape** đúng ký tự `"`, `\`, xuống dòng và ký tự điều khiển; không nối dữ liệu không tin cậy vào string literal mà không xử lý.
- Đóng `Writer` hoặc `OutputStream` trước khi chờ compiler biên dịch source mới.
- Dùng originating elements để công cụ build có thêm quan hệ nguồn – sản phẩm.
- Không tạo cùng một qualified name nhiều lần trong một processing run.

Trong bài lab, tên đơn giản của class như `Hello` là Java identifier hợp lệ, nên phần sinh chuỗi `Generated for Hello` an toàn. Processor tổng quát sinh code từ giá trị annotation dạng user input phải dùng công cụ escape/code generation đáng tin hoặc kiểm tra dữ liệu chặt chẽ.

## 6. Filer.createResource: package, relativeName và output location

Chữ ký cần nhớ:

~~~java
FileObject createResource(
    JavaFileManager.Location location,
    CharSequence pkg,
    CharSequence relativeName,
    Element... originatingElements
) throws IOException;
~~~

Đây là **chữ ký API được rút gọn để giải thích**, không phải một method cần chép nguyên vào class của người học.

Các thành phần:

- **`location`**: một nơi output được hỗ trợ, thường `StandardLocation.CLASS_OUTPUT` hoặc `SOURCE_OUTPUT`.
- **`pkg`**: tên package dùng để bố trí resource theo cấu trúc package; dùng `""` nếu resource nằm ở root của location.
- **`relativeName`**: tên tài nguyên tương đối bên trong package/location, dùng dấu `/` giữa các thành phần.
- **`originatingElements`**: những khai báo gốc khiến resource được sinh, hữu ích cho build tools.
- **`FileObject`**: cho phép `openWriter()`, `openOutputStream()`; **không mở hai stream khác nhau để ghi vào cùng một file một cách tùy tiện**.

Ví dụ A, resource chung ở root class output:

~~~java
filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "",
        "META-INF/acme/index.txt",
        origin
);
~~~

Đường dẫn dưới `-d build/classes`:

~~~text
build/classes/META-INF/acme/index.txt
~~~

Ví dụ B, resource tương ứng package `com.acme`:

~~~java
filer.createResource(
        StandardLocation.CLASS_OUTPUT,
        "com.acme",
        "config/defaults.properties",
        origin
);
~~~

Đường dẫn dưới class output:

~~~text
build/classes/com/acme/config/defaults.properties
~~~

Các đoạn ví dụ A/B là **fragment của processor**, giả sử `filer`, `origin` và import `StandardLocation` tồn tại. Không coi `pkg` là một đường dẫn file tùy ý: dùng package name của Java, không viết `com/acme` vào tham số này.

### Ghi UTF-8 và tài nguyên nhị phân

`openWriter()` sử dụng character encoding do môi trường JavaFileManager/compiler cung cấp. Để kiểm soát tuyệt đối encoding cho tài nguyên giao tiếp giữa nhiều hệ thống, có thể ghi byte UTF-8 qua `openOutputStream()`:

~~~java
byte[] bytes = "status=generated\n"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
try (java.io.OutputStream out = resource.openOutputStream()) {
    out.write(bytes);
}
~~~

Fragment trên cần biến `resource` là `FileObject` vừa tạo, không phải chương trình độc lập. Với payload JSON, protobuf hoặc nhị phân, hãy chọn encoding/serializer có quy ước rõ ràng. Khi tạo file mới, nội dung và vị trí resource phải nhất quán với cách ứng dụng tìm bằng `ClassLoader.getResource(...)`.

### Đọc resource đã có

`Filer.getResource(...)` dùng để lấy `FileObject` cho resource đang tồn tại trong vị trí compiler hỗ trợ. Cần phân biệt với `createResource(...)`; API được thiết kế để compiler quản lý các file tạo mới, **không phải** để processor viết rồi đọc lại cùng file tùy ý như cache có thể ghi đè. Một số vị trí và file đã tạo trong cùng run bị giới hạn truy cập, nên tránh quy trình “create → reopen để sửa” hay “create lại nếu nội dung khác”.

## 7. Rounds, file trùng và FilerException

Annotation processing có thể có nhiều round, đặc biệt khi processor tạo `.java` mới. Mỗi round dùng `RoundEnvironment` để báo phần tử gốc/annotated hiện tại và trạng thái. Đoạn code thường có:

~~~java
if (roundEnv.processingOver()) {
    return true;
}
~~~

Dòng trên tránh sinh file mới ở round cuối trong ví dụ. Khi một processor tạo file Java ở một round, compiler có thể xem file đó trong round kế tiếp. Một resource thuần túy không tự khiến compiler phát hiện một type mới.

### Filer kiểm soát việc tạo cùng một path nhiều lần

Ví dụ **cố ý sai** trong một processor:

~~~java
filer.createSourceFile("demo.Generated");
filer.createSourceFile("demo.Generated"); // Lỗi tạo lại cùng file.
~~~

Thông thường lần gọi thứ hai gây `FilerException` (lớp con của `IOException`), do file có tên đó đã được tạo trong cùng processing run. Không chữa bằng cách bắt exception rồi bỏ qua vô điều kiện: cần hiểu **vì sao** processor muốn tạo hai lần.

Tình huống dễ gặp:

- Hai type annotated có cùng simple name trong cùng package và thuật toán generator tạo chung một output name.
- Một processor tạo cùng tệp ở hai processing rounds.
- Hai processors cùng cố sinh một class/resource với cùng tên và location.
- Một processor muốn viết đè file source là input gốc.
- Incremental build để lại output cũ khiến việc xử lý khác biệt tùy build tool, hoặc generator có logic không ổn định.

**Quy tắc đúng:** xác định mỗi output name duy nhất, quyết định processor nào sở hữu nó và tạo một lần trong một compiler processing run. Nếu nhiều annotated elements góp vào một resource index, thu thập thông tin rồi **ghi một resource tổng hợp một lần**.

### State của processor và xử lý nhiều round

Processor instance có thể giữ state giữa các round trong cùng một lần chạy. Trong lab, `resourceCreated` ngăn tạo lại `META-INF/lesson/generated.txt`. Đừng giả định **mọi** instance, build daemon hoặc compilation invocation dùng lại state giống nhau giữa các lần build.

Có hai kiểu thường gặp:

- **Isolating output**: mỗi annotated element sinh một tệp riêng như `HelloCompanion.java`. Origin nên là element đó.
- **Aggregating output**: nhiều annotated elements đóng góp vào một tệp index. Phải thiết kế thời điểm ghi và origins sao cho output không mất dữ liệu đến từ round muộn.

Các thuật ngữ isolating/aggregating thường được build tools dùng để phân loại processor phục vụ incremental compilation. Chúng không phải hai phương thức của `Filer`. Muốn tương thích incremental build, cần tuân thủ hợp đồng cụ thể của Gradle/Maven/IDE và kiểm thử thay đổi/xóa input; chỉ truyền `originatingElements` là chưa đủ.

## 8. Source được sinh có được biên dịch tự động không?

Trong một lần `javac` có annotation processing, source do `Filer.createSourceFile` tạo có thể được compiler đưa vào các vòng xử lý và biên dịch, như `HelloCompanion.java` ở ví dụ.

Tuy nhiên, cần nhớ ba điểm:

1. **`-proc:only`** chỉ chạy annotation processing, không thực hiện biên dịch class như bình thường; có source sinh ra nhưng chưa chắc có `HelloCompanion.class`.
2. **`-proc:none`** tắt annotation processing. Trên build sạch, source `Hello.java` tham chiếu class chưa được sinh có thể báo `cannot find symbol`.
3. **Tùy build tool**, generated sources có thể được xử lý ở tác vụ compiler kế tiếp thay vì trực tiếp trong cùng câu lệnh `javac`. Quan sát command thực tế và thư mục output để xác định pipeline.

Ví dụ kiểm tra compile với processor tường minh:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp build/companion-processor.jar \
  -processorpath build/companion-processor.jar \
  -processor demo.processor.CompanionProcessor \
  -s build/generated -d build/classes \
  src/app/demo/app/Hello.java
~~~

Đây là lệnh tương tự mục 4, giả định processor đã được đóng JAR và thư mục output tồn tại. Nếu lệnh thành công, kiểm tra cả generated source **và** generated class; chỉ tồn tại file `.java` chưa đủ để chứng minh ứng dụng chạy được.

## 9. Processor path, annotation API và discovery

Ở bản lab, processor JAR chứa cả annotation type và class processor. Ta tách rõ:

- **`-processorpath build/companion-processor.jar`** cho compiler biết nơi tìm **processor executable**.
- **`-cp build/companion-processor.jar`** cho compiler biết nơi tìm kiểu `demo.api.GenerateCompanion` mà `Hello.java` import.
- **`-processor demo.processor.CompanionProcessor`** gọi processor **theo tên**, không phụ thuộc compiler tự phát hiện nó.

Nếu bỏ `-cp` trong cấu hình không có annotation trên đường tìm kiếm, `Hello.java` không tìm được `GenerateCompanion` dù processor path có thể chứa class ấy. Ngược lại, chỉ có annotation trên compile classpath không bảo đảm processor được kích hoạt khi build.

### Service registration cho processor

Có thể đóng file sau vào JAR processor:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung là tên đầy đủ của processor:

~~~text
demo.processor.CompanionProcessor
~~~

Khi cơ chế discovery được kích hoạt và processor được đặt trên đường tìm kiếm processor, `javac` có thể sử dụng file `META-INF/services` để phát hiện processor. Tuy nhiên behavior mặc định về việc tự phát hiện processor có thể thay đổi theo bản JDK, cấu hình và công cụ build. Với bài lab, chọn **`-processor` tường minh** để loại bỏ yếu tố này.

Nếu dùng Maven/Gradle, cấu hình annotation processor dependency riêng (nếu build plugin hỗ trợ) thay vì đưa mọi processor lên runtime classpath. Processor thực thi **mã tại build-time** và có thể truy cập hệ thống file/môi trường của tiến trình build; cần kiểm soát nguồn dependency đáng tin.

## 10. Khác biệt giữa createSourceFile và biến đổi AST

Một processor JSR 269 xem kiểu thông qua `TypeElement` và mô hình `javax.lang.model`. Nó có thể đọc annotation, method, field và type signatures, nhưng API chuẩn **không cung cấp `TypeElement.addMethod(...)`** để thay đổi trực tiếp class `Hello`.

Kết quả của lab:

~~~text
Đầu vào: Hello.java
           |
           +--> Class Hello vẫn chứa main() như source
           |
           +--> Filer tạo type mới HelloCompanion
                   |
                   +--> static message()
~~~

Nếu yêu cầu là “thêm getter vào chính class Hello dù source không có getter”, `Filer.createSourceFile("demo.app.HelloCompanion", ...)` **không** thực hiện thao tác đó. Cần chiến lược khác: sinh subclass/helper, sinh toàn bộ source qua template, dùng compiler-specific AST extension hoặc bytecode transformation. Những cơ chế này có hợp đồng và rủi ro tương thích riêng, không thuộc quyền sửa AST chuẩn của `Filer`.

Tương tự, `createClassFile(...)` tạo **một class file mới**; nó không phải cách tiện lợi để “vá” lại bytecode của một class input đã tồn tại trong cùng compilation. Hệ thống biến đổi bytecode có API và lifecycle khác.

## 11. Ghi diagnostic khi sinh file thất bại

Trong bài lab, lỗi I/O sinh source được báo bằng:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Cannot generate " + qualified + ": " + ex.getMessage(),
        element
);
~~~

Đây là **mã trong method `process`**, với các biến tương ứng. Gắn `element` giúp compiler có thể chỉ vị trí khai báo liên quan. `Diagnostic.Kind.ERROR` thường khiến compilation thất bại; phù hợp khi generated type hoặc resource là điều kiện để ứng dụng biên dịch/chạy đúng.

Phân loại diagnostic:

| Kind | Khi nào dùng |
| --- | --- |
| `NOTE` | Thông tin phục vụ debug/tracing nếu cần |
| `WARNING` | Tình huống đáng chú ý nhưng chưa cần dừng build |
| `MANDATORY_WARNING` | Cảnh báo mà công cụ cần hiển thị theo hợp đồng |
| `ERROR` | Đầu vào annotation sai, output bắt buộc không tạo được, hoặc không bảo đảm kết quả chính xác |

Không làm mất cause khi báo lỗi; nên đưa tên generated type/path và message I/O để người dùng biết lỗi xảy ra ở output nào. Tuy nhiên tránh đưa nội dung bí mật của môi trường build vào diagnostic.

### Một processor nên phản ứng thế nào khi có lỗi?

- Nếu annotation đặt sai loại khai báo: báo lỗi ngay tại element, không tạo output không hợp lệ.
- Nếu output name trùng: báo lỗi có ý nghĩa thay vì nuốt `FilerException`.
- Nếu source generation thất bại giữa chừng: đóng stream qua `try-with-resources` và báo lỗi.
- Nếu thiếu dependency của generator: sửa processor path/compile path, không tìm cách gọi reflection runtime để “tự khắc phục”.
- Nếu build đang bị lỗi ở round hiện tại: có thể kiểm tra `roundEnv.errorRaised()` và hạn chế sinh những output không đáng tin, tùy chính sách processor.

## 12. Thiết kế resource index dùng được ở runtime

Giả sử processor cần sinh file liệt kê component, route, mapper hoặc service implementation. Một pattern phổ biến là:

~~~text
META-INF/my-framework/components.idx
  demo.app.HelloCompanion
  demo.app.OtherCompanion
~~~

Đây là **minh họa resource index**, không phải nội dung thực của lab một class ở mục 4. Ưu điểm là runtime có thể đọc file metadata thay vì quét mọi class bằng reflection.

Để resource index bền vững:

1. Định nghĩa định dạng (UTF-8, newline, comment, escaping) rõ ràng.
2. Xác định có một index trên mỗi module/JAR hay nhiều file cùng tên cần hợp nhất.
3. Khi nhiều phần tử đóng góp, chọn chiến lược aggregate không bỏ sót round muộn.
4. Tránh trùng dòng và có thể sắp xếp tên để build tái lập.
5. Đóng vào `CLASS_OUTPUT` để được đóng cùng sản phẩm runtime khi build pipeline hỗ trợ.
6. Nếu đóng **fat/uber JAR**, kiểm tra công cụ đóng gói có merge resource cùng tên hay chỉ giữ một file.
7. Khi runtime dùng `ClassLoader.getResource(...)`, chỉ lấy một URL phù hợp; nếu cần metadata từ nhiều JAR, dùng `getResources(...)` và gộp có kiểm soát.

**Đừng nhầm với `META-INF/services/<service-interface>`.** Đây là định dạng metadata chuẩn để `ServiceLoader` tìm provider. Nếu viết `META-INF/services`, phải tuân thủ format, tên service và điều kiện constructor/provider/module theo cơ chế `ServiceLoader`; chỉ tạo một file bất kỳ trong `META-INF` không khiến JVM tự đăng ký service.

## 13. Filer trong incremental build và test

Trong build thật, generated source và resource là **sản phẩm** của một tập đầu vào. Nếu source gốc đổi/tên class bị xóa, build tool cần xác định phải tạo lại hoặc xóa output nào. Bài lab dùng thao tác thủ công nên việc dọn output có thể ảnh hưởng kết quả:

~~~bash
# Trên Linux/macOS: làm sạch riêng thư mục build của bài lab
rm -rf build
~~~

Lệnh trên **chỉ là hướng dẫn thủ công**, không nên chạy nếu đang ở nhầm thư mục hoặc có dữ liệu quan trọng trong `build`. Trên Windows có thể dùng chức năng clean của build tool hoặc xóa chính xác thư mục output của lab; không xóa thư mục tùy ý.

### Kiểm thử processor

Một số ca cần test:

- Input hợp lệ sinh đúng tên qualified, package, method và resource.
- Input type không hợp lệ (ví dụ annotation đặt trên interface khi policy chỉ chấp nhận class) phát `ERROR`.
- Hai input tạo cùng output name được phát hiện và báo lỗi rõ.
- Cùng processor qua nhiều rounds không tự tạo trùng.
- Output Java biên dịch được ở source level mục tiêu.
- Resource thực sự nằm trên runtime classpath/JAR, đọc đúng encoding và đường dẫn.
- Incremental build sửa/xóa một annotated type có kết quả tương ứng; không để generated class/resource cũ gây false success.
- Build với Java compiler/JDK khác được processor công bố hỗ trợ.

Nếu test codegen bằng cách tìm `String.contains("Generated for Hello")`, đó chỉ là kiểm tra văn bản. Bài test đáng tin còn phải **compile generated source** và, khi phù hợp, chạy hành vi trên runtime target.

## 14. Các lỗi thường gặp khi dùng Filer

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: HelloCompanion` | Processor không được chạy, không sinh file, source output chưa compile hoặc class stale | Xác nhận `-processor`, processor path, `-s`, `-d` và diagnostic |
| `FilerException: Attempt to recreate a file ...` | Cố tạo cùng path nhiều lần trong một processing run hoặc trùng input | Xem round, tên output, phối hợp processors; chỉ create một lần |
| Có `HelloCompanion.java` nhưng thiếu `.class` | Dùng `-proc:only`, compile dở hoặc build chưa compile generated source | Chạy pha compile phù hợp và xem compiler errors |
| Có resource trong `build/generated` nhưng runtime không thấy | Đặt sai location hoặc không copy resource vào runtime classpath | Dùng `CLASS_OUTPUT` nếu tài nguyên phục vụ runtime; kiểm tra JAR |
| `getResourceAsStream(...) == null` | Sai đường dẫn, resource không được đóng gói, loader khác | Dò JAR bằng `jar --list`, kiểm tra classpath/loader |
| Tên package class sinh không đúng | `createSourceFile` name không khớp package declaration | Dùng qualified name và sinh package phù hợp |
| Processor không được phát hiện | Thiếu `-processor`, sai service file hoặc processor path | Chỉ định processor tường minh trong build |
| Processor chạy nhưng không có phần tử annotated | Annotation name/import sai, input không nằm trong compilation, target sai | Đọc `RoundEnvironment` và log `Messager` |
| Generated source chứa chuỗi Java không hợp lệ | Không escape giá trị annotation khi sinh code | Dùng serializer/escaping thích hợp; compile generated source |
| Build lại nhưng dữ liệu index sai/thiếu | Aggregating logic không xử lý round muộn, output stale | Thiết kế tổng hợp một lần, kiểm thử clean/incremental |
| Resource UTF-8 bị lỗi dấu | Encoding writer/reader không nhất quán | Ghi byte UTF-8 hoặc cấu hình compiler encoding rõ |
| Compiler cũ cảnh báo source version processor | `@SupportedSourceVersion` không hợp với source level chạy | Dùng processor version được hỗ trợ, cấu hình source/target tương ứng |

Khi điều tra, bắt đầu từ **kết quả trên disk**: kiểm tra file generated source, generated `.class` và resource, rồi mới tìm lỗi runtime. Tránh sửa runtime classpath nếu nguồn chưa được tạo ở compile-time.

## 15. Bài tập tự kiểm tra có đáp án

**Bài 1.** Với `-s build/generated`, processor gọi `createSourceFile("com.demo.MapperImpl", origin)`. Tệp thường được sinh ở đâu?

**Đáp án:** `build/generated/com/demo/MapperImpl.java`, với package declaration `package com.demo;` trong source.

**Bài 2.** Processor cần tạo một file `META-INF/config/index.txt` để ứng dụng đọc sau khi đóng JAR. Nên dùng location nào?

**Đáp án:** Thường dùng `StandardLocation.CLASS_OUTPUT` với package rỗng và relative name `META-INF/config/index.txt`; xác minh pipeline đóng gói copy resource vào JAR.

**Bài 3.** Processor gọi `createSourceFile("demo.Generated")` ở round 1 và round 2 cùng compilation. Có hợp lệ không?

**Đáp án:** Không. Filer quản lý output names trong một processing run; cố tạo lại cùng file thường dẫn đến `FilerException`.

**Bài 4.** `@GenerateCompanion` có retention SOURCE. Processor có thể đọc nó không? Runtime reflection có thấy nó trên `Hello.class` không?

**Đáp án:** Processor có thể đọc từ mô hình compilation. Runtime reflection thông thường không thấy SOURCE-retention annotation trong class file.

**Bài 5.** `createClassFile(...)` có cho phép ghi source text `public class Demo {}` rồi tự biến thành bytecode không?

**Đáp án:** Không. Phương thức dùng để sinh class file hợp lệ; muốn sinh source text rồi nhờ compiler biên dịch, dùng `createSourceFile(...)`.

**Bài 6.** Vì sao đã có processor JAR trên `-processorpath` mà source `Hello.java` vẫn báo không nhận `demo.api.GenerateCompanion`?

**Đáp án:** Processor path dành cho nạp processor; annotation type source import còn cần xuất hiện trong đường tra kiểu của compilation, ví dụ compile classpath thích hợp.

**Bài 7.** `originatingElements` có tự bảo đảm incremental build xóa mọi generated file cũ khi input bị xóa không?

**Đáp án:** Không. Nó cung cấp quan hệ nguồn – output, còn logic incremental/cache/cleanup do build tool và processor phối hợp thực hiện.

**Bài 8.** Khi hai JAR đóng góp metadata với cùng tên resource, `ClassLoader.getResource(...)` có gộp nội dung cả hai không?

**Đáp án:** Không. `getResource` trả một resource phù hợp; nếu cần tìm nhiều resource, dùng `getResources` và áp dụng logic merge rõ ràng.

## Ghi nhớ

- **`Filer` là API xuất sản phẩm của annotation processor**: tạo source, class file và resource trong build; không sửa AST của class gốc.
- **`createSourceFile`** nhận tên qualified type; compiler có thể biên dịch source mới trong round tiếp theo.
- **`createResource`** nhận location, package, relative name; `CLASS_OUTPUT` thích hợp cho nhiều tài nguyên cần có trong runtime JAR.
- **`-s` và `-d` khác nhau**: `-s` cho generated source, `-d` cho class file và `CLASS_OUTPUT` resource.
- **Đóng Writer/OutputStream** sau khi ghi; không tạo cùng một path nhiều lần; báo `FilerException` và IO errors bằng `Messager`.
- **Round và originating elements** quan trọng đối với codegen, đặc biệt khi sinh resource tổng hợp và incremental build.
- **Processor path và compile classpath khác vai trò**; hãy cấu hình processor tường minh và xác minh generated `.java`, `.class`, resource trong artifact.
