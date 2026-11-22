# Sinh một lớp chỉ mục từ các phần tử được đánh dấu bằng annotation processor

Bài thực hành tổng hợp này xây dựng một **annotation processor Java (JSR 269)** để tìm những lớp được đánh dấu `@Indexed` trong quá trình biên dịch, rồi **tự sinh một lớp Java chứa danh sách tên lớp**. Sau khi compile, ứng dụng gọi lớp được sinh ra như mã nguồn Java bình thường, thay vì phải tự viết danh sách hoặc dùng runtime classpath scanning.

Ví dụ có ba lớp:

```java
@Indexed class Alpha {}
@Indexed class Beta {}
class Gamma {}
```

Kết quả mong muốn là một lớp nguồn được tạo ra tự động:

```java
package demo.generated;

public final class IndexedTypes {
    private IndexedTypes() {}
    public static java.util.List<String> names() {
        return java.util.List.of(
            "demo.app.Alpha",
            "demo.app.Beta"
        );
    }
}
```

`IndexedTypes.names()` phải chứa **chính xác hai phần tử**, theo thứ tự xác định, **không có `Gamma`**. Đây là một **chỉ mục tĩnh được sinh ở compile time**, không phải Registry tự đăng ký khi class loading và cũng không phải cơ chế Java Reflection đi quét toàn bộ classpath lúc chạy.

Bài học minh họa trọn chu trình **định nghĩa annotation → lập trình processor → tìm các `Element` có annotation → dùng `Filer` tạo file `.java` → compiler biên dịch file được sinh → kiểm tra kết quả**. Mã chính dùng Java 17+, chỉ cần JDK, không phụ thuộc Maven, Gradle, Spring hoặc thư viện bên ngoài.

## 1. Bài toán và kiến trúc

Trong nhiều ứng dụng, cần tập hợp danh sách các loại đã được đánh dấu bởi annotation để:

- Có một danh mục các component/module được khai báo trong source.
- Tạo metadata cho routing, plugin, serialization, hoặc tài liệu hóa.
- Tránh duy trì một danh sách tên lớp bằng tay dễ thiếu sót.
- Tránh phải quét classpath bằng Reflection khi chương trình khởi động.
- Phát lỗi compile-time nếu annotation được gắn trên phần tử không hỗ trợ.

Giải pháp dùng hai phần chính:

1. **`@Indexed`**: annotation đánh dấu một kiểu cần đưa vào chỉ mục.
2. **`IndexProcessor`**: compiler plugin được javac gọi, tìm các phần tử có `@Indexed` rồi sinh lớp **`demo.generated.IndexedTypes`**.

Sơ đồ:

```text
Alpha.java          Beta.java           Gamma.java
   @Indexed            @Indexed            (không đánh dấu)
      |                    |                     |
      +--------------------+---------------------+
                           |
                 javac + IndexProcessor
                           |
            RoundEnvironment.getElementsAnnotatedWith
                           |
                     Alpha, Beta
                           |
                TypeElement.getQualifiedName
                           |
                TreeMap để sắp xếp ổn định
                           |
                 Filer.createSourceFile
                           |
        build/generated/demo/generated/IndexedTypes.java
                           |
                   javac biên dịch tiếp
                           |
           build/classes/demo/generated/IndexedTypes.class
                           |
                     demo.app.App
                           |
              IndexedTypes.names()
                 [Alpha, Beta]
```

**Giới hạn có chủ đích:** bài thực hành minh họa **các lớp thông thường ở mức top-level**, không phải mọi kiểu `Element` của Java. Annotation `@Target(TYPE)` cho phép cả interface/enum/record ở mức cú pháp, nhưng processor sẽ chỉ chấp nhận `ElementKind.CLASS`; những loại khác bị báo lỗi nếu đánh dấu. Phần cuối giải thích cách mở rộng cho phương thức, trường, nested classes, nhiều module và nhiều processing rounds.

## 2. Cấu trúc thư mục cần tạo

Đặt các file:

```text
index-demo/
├── src/
│   └── demo/
│       ├── marker/
│       │   └── Indexed.java
│       ├── processor/
│       │   └── IndexProcessor.java
│       └── app/
│           ├── Alpha.java
│           ├── Beta.java
│           ├── Gamma.java
│           └── App.java
└── build/
    ├── processor/  (javac sinh lớp processor và annotation)
    ├── generated/  (Filer sinh source IndexedTypes.java)
    └── classes/    (javac sinh lớp ứng dụng và IndexedTypes.class)
```

Các đường dẫn `build/...` là output và sẽ được tạo ở bước compile. Trong demo, ta đặt annotation và processor ở các package riêng, nhưng biên dịch chúng vào cùng một thư mục classes đầu tiên để giảm cấu hình.

`demo.generated.IndexedTypes` **chưa tồn tại trong source ban đầu**. Đừng tự tạo file với tên này trong `src`: mục tiêu là để processor sinh file qua `Filer`, và tạo trùng file có thể gây lỗi `FilerException`.

## 3. Indexed.java — annotation để đánh dấu lớp

File **`src/demo/marker/Indexed.java`**:

```java
package demo.marker;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Indexed {
}
```

Giải thích:

- `@interface Indexed` định nghĩa annotation không có phần tử dữ liệu; chỉ cần **có hoặc không**.
- `@Target(TYPE)` cho phép dùng trên các khai báo kiểu. Trong processor ta sẽ lọc chỉ lớp thông thường.
- `@Retention(SOURCE)` là đủ vì processor đọc annotation **trong quá trình javac biên dịch**. Không cần giữ marker này để Reflection runtime đọc.
- `Indexed` được khai báo `public` ở package `demo.marker` để mã ứng dụng có thể `import demo.marker.Indexed`.

Khi dùng:

```java
@Indexed
public class Alpha {
}
```

compiler có thể cung cấp đối tượng `TypeElement` của `Alpha` tới processor khi nó xử lý source. Annotation không tự tạo chỉ mục, không tự đăng ký lớp và không tự chạy code trong `Alpha`.

### SOURCE hay RUNTIME?

Nếu mục tiêu duy nhất là **sinh một danh sách trong lúc compile**, `SOURCE` giữ thiết kế đơn giản và không bắt ứng dụng giữ marker trong class file. Nếu một hệ thống khác **cần đọc chính annotation đó bằng Reflection lúc chạy**, có thể chọn `RUNTIME`. Hai nhu cầu khác nhau:

| Nhu cầu | Cơ chế | Retention đủ dùng |
| --- | --- | --- |
| Processor tìm lớp khi compile | Java annotation processing / `RoundEnvironment` | `SOURCE` |
| App gọi `Class.getAnnotation(Indexed.class)` lúc chạy | Java Reflection | `RUNTIME` |
| App sử dụng danh sách tên từ lớp chỉ mục đã sinh | `IndexedTypes.names()` | Không cần marker tồn tại ở runtime |

Lớp chỉ mục đã được sinh chứa **chuỗi tên lớp**. Nội dung đó có thể tồn tại khi chạy kể cả annotation nguồn `@Indexed` đã không còn trong file `.class`.

## 4. IndexProcessor.java — tìm và lọc phần tử được đánh dấu

File đầy đủ **`src/demo/processor/IndexProcessor.java`**:

```java
package demo.processor;

import demo.marker.Indexed;
import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Map;
import java.util.TreeMap;
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

@SupportedAnnotationTypes("demo.marker.Indexed")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class IndexProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            java.util.Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated) {
            return true;
        }

        Map<String, Element> found = new TreeMap<>();

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Indexed.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Indexed can only mark ordinary classes in this demo",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            found.put(type.getQualifiedName().toString(), type);
        }

        if (found.isEmpty()) {
            return true;
        }

        try {
            JavaFileObject file = processingEnv.getFiler().createSourceFile(
                    "demo.generated.IndexedTypes",
                    found.values().toArray(new Element[0]));

            try (Writer out = file.openWriter()) {
                out.write("package demo.generated;\n\n");
                out.write("public final class IndexedTypes {\n");
                out.write("    private IndexedTypes() {}\n");
                out.write("    public static java.util.List<String> names() {\n");
                out.write("        return java.util.List.of(\n");

                var names = new ArrayList<>(found.keySet());
                for (int i = 0; i < names.size(); i++) {
                    out.write("            \"" + names.get(i) + "\"");
                    out.write(i + 1 == names.size() ? "\n" : ",\n");
                }

                out.write("        );\n");
                out.write("    }\n");
                out.write("}\n");
            }

            generated = true;
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Could not create demo.generated.IndexedTypes: "
                            + ex.getMessage());
        }

        return true;
    }
}
```

Đây là một annotation processor **runnable** cho bài tập với các lớp top-level. Nó tạo một nguồn Java chuẩn thông qua API `Filer`, không ghi trực tiếp vào thư mục source gốc và không mở đường dẫn tương đối bằng `new FileWriter(...)`.

### 4.1. Cấu hình processor

```java
@SupportedAnnotationTypes("demo.marker.Indexed")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
```

Hai meta-annotation này khai báo loại annotation processor hỗ trợ và source level. `@SupportedAnnotationTypes` cần **tên đầy đủ của annotation type**, không phải tên `IndexProcessor` hay tên file source.

`IndexProcessor` kế thừa `AbstractProcessor`, nên cung cấp được `processingEnv`, `Messager`, `Filer` và các tiện ích mô hình ngôn ngữ. Nó chạy khi **javac chọn processor**, không phải khi ứng dụng gọi `main`.

### 4.2. Tìm phần tử với RoundEnvironment

```java
roundEnv.getElementsAnnotatedWith(Indexed.class)
```

trả các `Element` mà compiler xác định được đánh dấu `@Indexed` trong round hiện tại. `Element` là **mô hình khai báo trong compiler**, không phải instance của lớp ứng dụng hay runtime `Class<?>`.

Trong ví dụ, `Alpha` và `Beta` là các `TypeElement` vì chúng là khai báo kiểu. `Gamma` không có annotation nên không được trả về.

Lời gọi trên được dùng **trong processor**, nơi `Indexed.class` là class của annotation type mà processor đã được biên dịch tham chiếu. Điều đó không có nghĩa những lớp `Alpha` và `Beta` đã được load bởi JVM đang chạy processor.

### 4.3. Lọc ElementKind

```java
if (element.getKind() != ElementKind.CLASS) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "@Indexed can only mark ordinary classes in this demo",
            element);
    continue;
}
```

`@Target(TYPE)` cho phép annotation được viết trên nhiều loại khai báo kiểu. Nhưng mục tiêu **bài demo** là tạo chỉ mục những class thông thường. Processor chủ động báo lỗi đối với các `ElementKind` khác.

`Diagnostic.Kind.ERROR` làm javac không thể coi build là biên dịch hợp lệ trong tình huống này. Mã ứng dụng nên sửa annotation usage hoặc mở rộng logic processor có chủ đích; không nên im lặng bỏ qua nếu đó là vi phạm hợp đồng.

### 4.4. Lấy tên loại từ TypeElement

```java
TypeElement type = (TypeElement) element;
String qualifiedName = type.getQualifiedName().toString();
```

Với lớp top-level `Alpha` trong package `demo.app`, tên được lấy là `demo.app.Alpha`. Đây là **qualified name/canonical-like source name** của kiểu, không phải file path hay đường dẫn package dạng dấu gạch chéo.

Không dùng:

```java
Class.forName("demo.app.Alpha")
```

trong processor để tìm lớp đang biên dịch. Chúng có thể chưa có `.class`, và không nên yêu cầu runtime loader tạo instance để biết metadata source. `TypeElement` giải quyết đúng bài toán compile-time.

**Giới hạn nested classes:** `getQualifiedName()` có thể trả tên nguồn dạng `demo.app.Outer.Inner`, trong khi `Outer.Inner.class.getName()` sử dụng **binary name** với `\$` (ví dụ `demo.app.Outer$Inner`). Bài dùng class top-level; nếu muốn chỉ mục dạng tên có thể truyền thẳng cho `Class.forName`, với kiểu lồng nên xem `Elements.getBinaryName(TypeElement)` và kiểm thử riêng. Không đánh đồng mọi kiểu tên Java.

### 4.5. Vì sao dùng TreeMap?

```java
Map<String, Element> found = new TreeMap<>();
found.put(type.getQualifiedName().toString(), type);
```

Một `TreeMap` sắp xếp theo thứ tự từ điển của key và đồng thời chống trùng **cùng tên**. Điều này cho đầu ra **ổn định** thay vì phụ thuộc thứ tự compiler tình cờ duyệt các `Element`.

Mảng `names` được tạo từ `found.keySet()`, vì vậy với hai lớp có tên `demo.app.Alpha` và `demo.app.Beta`, chỉ mục có `Alpha` trước `Beta`.

Ổn định thứ tự giúp test tái lập, diff của file được sinh dễ đọc và tránh làm hệ thống build phát hiện thay đổi giả chỉ vì annotation processor chạy theo một thứ tự duyệt khác.

### 4.6. Tạo file bằng Filer

```java
JavaFileObject file = processingEnv.getFiler().createSourceFile(
        "demo.generated.IndexedTypes",
        found.values().toArray(new Element[0]));
```

`createSourceFile` nhận **tên fully qualified của lớp sẽ sinh**. Javac quyết định output path theo `-s` hoặc cấu hình build, không nên hardcode đường dẫn thư mục trong processor.

Danh sách `Element` phía sau là **originating elements**: metadata liên kết file được sinh với những khai báo đầu vào đã góp phần tạo ra nó. Điều này hữu ích cho một số cơ chế theo dõi phụ thuộc/incremental compilation; không có nghĩa compiler bắt buộc gộp mọi dependency giống nhau trên mọi build tool.

Cú pháp:

```java
try (Writer out = file.openWriter()) {
    // Ghi source code Java hợp lệ vào JavaFileObject.
}
```

dùng try-with-resources để đóng writer ngay khi xong. Nếu không đóng, compiler có thể chưa nhận được file source hoàn chỉnh đúng thời điểm.

### 4.7. Sinh class chỉ mục

Processor ghi:

```java
out.write("package demo.generated;\n\n");
out.write("public final class IndexedTypes {\n");
out.write("    private IndexedTypes() {}\n");
out.write("    public static java.util.List<String> names() {\n");
out.write("        return java.util.List.of(\n");
```

rồi ghi mỗi tên lớp vào một literal string. Sau đó đóng `List.of(...)`, method và class.

Lớp được sinh:

- `final`: không dự kiến để ứng dụng kế thừa.
- Constructor `private`: chỉ chứa API tĩnh, không cần tạo instance.
- `names()` trả `List<String>` bất biến qua `List.of`.
- Dữ liệu của phương thức là **compile-time index**, không phải kết quả tự động quét classpath tại runtime.

Vì code sinh tên lớp dưới dạng chuỗi, nó **không khởi tạo `Alpha` hay `Beta`**; kể cả khi code có dòng `"demo.app.Alpha"`, nó không tương đương gọi `new Alpha()`.

**An toàn khi sinh source:** ví dụ lấy tên trực tiếp từ `TypeElement` do compiler xác định, thuộc phạm vi kiểu top-level. Nếu mở rộng generator để đưa dữ liệu annotation do người dùng nhập vào string literal, bắt buộc **escape dấu nháy, backslash, ký tự điều khiển** và kiểm tra giá trị trước khi ghép vào source để tránh tạo file Java sai cú pháp.

### 4.8. Tránh tạo cùng file hai lần

```java
private boolean generated;
```

và:

```java
if (roundEnv.processingOver() || generated) {
    return true;
}
```

giúp processor không gọi lại `Filer.createSourceFile("demo.generated.IndexedTypes")` ở các round sau. JSR 269 có thể chạy **nhiều processing rounds**, đặc biệt khi vừa sinh thêm source.

Theo hợp đồng `Filer`, cố tạo lại cùng tên file trong một lần xử lý có thể gây `FilerException`. Vì vậy tránh ghi lại file hoặc cố mở lại file trong lần round sau.

**Giới hạn cần biết:** bộ demo cố ý tạo chỉ mục **trong round đầu tiên có các lớp được đánh dấu** và sau đó dừng tạo lại. Nếu một processor khác **sinh thêm `@Indexed` classes trong round muộn hơn**, index của bài demo **không tự bổ sung chúng**. Đối với dự án cần tập hợp mọi phát sinh qua nhiều round, hãy thiết kế chiến lược **aggregating processor** riêng, phân tách bước tổng hợp, hoặc dùng pipeline nhiều giai đoạn có kiểm soát. Đừng chỉ bỏ cờ `generated` để “cho chạy lại”, vì sẽ gặp lỗi tạo trùng file.

### 4.9. Xử lý lỗi ghi file

```java
} catch (IOException ex) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Could not create demo.generated.IndexedTypes: "
                    + ex.getMessage());
}
```

Những lỗi như file trùng, output path không ghi được hoặc lỗi I/O cần trở thành **compiler diagnostic** chứ không được âm thầm bỏ qua. Build phải thất bại khi generator cần thiết nhưng không thể tạo nguồn hợp lệ.

`process(...)` trả `true` ở đây để **claim loại annotation đã xử lý** trong round. Giá trị này không phải `boolean` báo “lớp chỉ mục đã được tạo thành công”; compiler sử dụng nó cho quy tắc phối hợp các processor.

## 5. Các lớp được đánh dấu và lớp không được đánh dấu

File **`src/demo/app/Alpha.java`**:

```java
package demo.app;

import demo.marker.Indexed;

@Indexed
public class Alpha {
}
```

File **`src/demo/app/Beta.java`**:

```java
package demo.app;

import demo.marker.Indexed;

@Indexed
public class Beta {
}
```

File **`src/demo/app/Gamma.java`**:

```java
package demo.app;

public class Gamma {
}
```

Đây là ba file riêng biệt, mỗi file chứa một lớp public cùng tên. `Alpha` và `Beta` được `IndexProcessor` chọn, `Gamma` không được đưa vào `found`.

Nếu bạn bỏ `@Indexed` khỏi `Beta`, chỉ mục được tạo trong **một build sạch** sẽ chỉ còn `Alpha`. Nếu thêm `@Indexed` vào `Gamma` rồi build sạch, nó sẽ được đưa vào danh sách theo thứ tự tên từ `TreeMap`.

**Khuyến nghị:** thực hiện clean build khi kiểm tra sự thay đổi tập lớp được đánh dấu. Vì file generated là sản phẩm build, output cũ không được coi là nguồn dữ liệu đáng tin cho một lần compile mới nếu task/build tool không xóa hoặc không quản lý nó đúng cách.

## 6. App.java — sử dụng lớp được sinh

File **`src/demo/app/App.java`**:

```java
package demo.app;

import demo.generated.IndexedTypes;

public class App {
    public static void main(String[] args) {
        System.out.println("Index entries=" + IndexedTypes.names().size());

        for (String name : IndexedTypes.names()) {
            System.out.println(name);
        }

        System.out.println("contains Alpha="
                + IndexedTypes.names().contains(Alpha.class.getName()));

        System.out.println("contains Gamma="
                + IndexedTypes.names().contains(Gamma.class.getName()));
    }
}
```

`App` import `demo.generated.IndexedTypes` mặc dù file `IndexedTypes.java` **chưa có trước khi compiler chạy**. Javac có thể nhận source do annotation processor tạo ra ở processing round phù hợp rồi biên dịch tiếp; đó là lý do **không cần copy file generated bằng tay** để ứng dụng dùng nó.

`IndexedTypes.names()` trả danh sách chuỗi:

```text
demo.app.Alpha
demo.app.Beta
```

`Alpha.class.getName()` là `demo.app.Alpha` và `Gamma.class.getName()` là `demo.app.Gamma` đối với những lớp top-level của ví dụ. App kiểm tra index chứa class được đánh dấu và không chứa class chưa đánh dấu.

Ứng dụng **không cần quét classpath**, **không đọc `@Indexed` bằng Reflection** và **không tự tạo instance của các class được lập chỉ mục**.

## 7. Biên dịch toàn bộ demo bằng javac

Chạy các lệnh trong thư mục gốc `index-demo`. Dùng JDK 17 trở lên.

### Bước 1 — tạo các thư mục output

Trên Linux/macOS hoặc shell Bash:

```bash
mkdir -p build/processor build/generated build/classes
```

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Force build/processor, build/generated, build/classes | Out-Null
```

### Bước 2 — biên dịch annotation API và processor

```bash
javac --release 17 -d build/processor \
  src/demo/marker/Indexed.java \
  src/demo/processor/IndexProcessor.java
```

Sau đó có:

```text
build/processor/demo/marker/Indexed.class
build/processor/demo/processor/IndexProcessor.class
```

Ở giai đoạn này processor chỉ **được biên dịch**, chưa chạy trên các lớp ứng dụng. Chúng ta chưa yêu cầu service discovery hoặc file `META-INF/services`.

### Bước 3 — biên dịch ứng dụng và chạy processor

```bash
javac --release 17 \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.IndexProcessor \
  -s build/generated \
  -d build/classes \
  src/demo/app/Alpha.java \
  src/demo/app/Beta.java \
  src/demo/app/Gamma.java \
  src/demo/app/App.java
```

Ý nghĩa:

| Tùy chọn | Vai trò |
| --- | --- |
| `-cp build/processor` | Cho source của app import được `demo.marker.Indexed` |
| `-processorpath build/processor` | Nơi javac tải `IndexProcessor` và phụ thuộc cần thiết |
| `-processor demo.processor.IndexProcessor` | Chỉ định **processor tường minh**; không cần file SPI cho ví dụ |
| `-s build/generated` | Thư mục lưu `.java` do `Filer.createSourceFile` tạo |
| `-d build/classes` | Thư mục lưu `.class` của ứng dụng **và nguồn được sinh** |
| `--release 17` | API/ngữ pháp/bytecode mục tiêu Java 17 |

**Điểm quan trọng:** không thêm `src/demo/generated/IndexedTypes.java` vào lệnh javac vì file đó không tồn tại trong source gốc. `IndexProcessor` tạo nó bằng `Filer`, javac nhận và biên dịch nó trong quy trình.

Các đoạn Bash dùng ký tự `\` ở cuối dòng để nối lệnh. Trong PowerShell, dùng một dòng dài hoặc dấu backtick nối dòng:

```powershell
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.IndexProcessor -s build/generated -d build/classes src/demo/app/Alpha.java src/demo/app/Beta.java src/demo/app/Gamma.java src/demo/app/App.java
```

### Bước 4 — chạy chương trình

```bash
java -cp build/classes demo.app.App
```

Stdout **chính xác** của chương trình:

```text
Index entries=2
demo.app.Alpha
demo.app.Beta
contains Alpha=true
contains Gamma=false
```

**Kiểm chứng thực nghiệm:** toàn bộ processor và application đã được biên dịch với `javac --release 17`; `App` chạy thành công và xuất đúng năm dòng phía trên. Các file thử nghiệm được tạo trong thư mục tạm phục vụ kiểm thử, không thay đổi source project.

## 8. Quan sát trực tiếp source được sinh

Sau khi chạy bước compile thứ hai, xem:

```bash
cat build/generated/demo/generated/IndexedTypes.java
```

Trên PowerShell:

```powershell
Get-Content build/generated/demo/generated/IndexedTypes.java
```

Nội dung đầy đủ dự kiến:

```java
package demo.generated;

public final class IndexedTypes {
    private IndexedTypes() {}
    public static java.util.List<String> names() {
        return java.util.List.of(
            "demo.app.Alpha",
            "demo.app.Beta"
        );
    }
}
```

Đây không phải một đoạn bạn viết trước trong thư mục source. Nó là kết quả mà `IndexProcessor` sinh qua `Filer`.

Sau khi compile xong, sẽ có cả:

```text
build/classes/demo/generated/IndexedTypes.class
```

Nếu source generated có nhưng class generated không có, hãy kiểm tra liệu javac có dừng vì lỗi compilation, đang dùng `-proc:only`, có chỉ định `-d` khác hoặc đang kiểm tra sai thư mục hay không.

### Vì sao sinh source thay vì trực tiếp viết bytecode?

`Filer.createSourceFile` là lựa chọn dễ học vì:

- Source Java sinh ra có thể đọc và kiểm tra như một file bình thường.
- Javac tiếp tục kiểm tra kiểu/cú pháp của source được sinh.
- Không phải tự biết cách mã hóa class-file/constant pool.
- Build tool có thể theo dõi file được sinh và originating elements khi được hỗ trợ.
- Debug đơn giản: so sánh file `.java` trong `build/generated` với output mong đợi.

Có thể dùng `Filer.createClassFile` trong các tình huống cần trực tiếp tạo bytecode, nhưng điều đó đòi hỏi kiến thức về định dạng class file và không cần thiết cho bài thực hành này.

## 9. Kiểm thử chỉ mục thay vì chỉ nhìn stdout

Một phương thức kiểm tra đơn giản là biến tên lớp thành một danh sách mong đợi rồi so trực tiếp:

```java
java.util.List<String> expected = java.util.List.of(
        "demo.app.Alpha", "demo.app.Beta");

java.util.List<String> actual = demo.generated.IndexedTypes.names();

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Index mismatch: expected=" + expected + ", actual=" + actual);
}
```

Đây là **snippet để đặt trong một test method hoặc trong `main`**, không phải file standalone độc lập. `List.equals` kiểm tra **số lượng, từng giá trị và thứ tự**, nên phát hiện cả thiếu phần tử, thừa phần tử và thứ tự sai.

Nên kiểm tra các ca sau:

| Ca | Input source | Kỳ vọng khi build sạch |
| --- | --- | --- |
| Hai class có `@Indexed` | `Alpha`, `Beta` | `[demo.app.Alpha, demo.app.Beta]` |
| Một class không có `@Indexed` | `Gamma` | Không có `Gamma` trong index |
| Chỉ một class đánh dấu | Chỉ `Alpha` | Index một phần tử |
| Đảo thứ tự truyền file cho javac | `Beta.java` rồi `Alpha.java` | Vẫn `Alpha` trước `Beta` do `TreeMap` |
| Gắn `@Indexed` lên interface | `interface Service` | Compile báo lỗi do policy của demo |
| Gắn `@Indexed` lên phương thức | `void run()` | Javac từ chối do `@Target(TYPE)` |
| Build lần hai không clean | Có thể còn output cũ | Không coi output cũ là chính xác khi thay tập source |
| Không có lớp nào được đánh dấu | Tập rỗng | Demo **không sinh `IndexedTypes`**; nếu App vẫn import nó, compile sẽ không hợp lệ |

**Vì sao ca “không có lớp nào” đáng chú ý?** Trong processor có `if (found.isEmpty()) return true;`, nghĩa là không có file chỉ mục. Thiết kế này phù hợp ví dụ tối giản, nhưng một ứng dụng luôn import `IndexedTypes` sẽ không compile khi hoàn toàn không có entry. Nếu yêu cầu index luôn tồn tại dù rỗng, bạn cần thay đổi hợp đồng generator: có thể khai báo index luôn sinh từ tập rỗng theo một vòng phù hợp, và kiểm thử kỹ nhiều processing rounds để tránh generate trùng.

## 10. Phân biệt Annotation Processor với Reflection runtime

Hai đoạn ý tưởng sau **không tương đương**.

**Trong compile-time processor:**

```java
for (Element e : roundEnv.getElementsAnnotatedWith(Indexed.class)) {
    // Đọc mô hình source/compiler.
}
```

**Trong runtime Reflection:**

```java
boolean present = Alpha.class.isAnnotationPresent(Indexed.class);
```

Với `@Retention(SOURCE)` ở ví dụ chính, truy vấn Reflection runtime trên `Alpha.class` không thấy lần sử dụng `@Indexed`. Nhưng chỉ mục `IndexedTypes` vẫn tồn tại vì đã được sinh trong build.

Tính chất cần hiểu:

- **Annotation processing:** compiler biết những source/element được xử lý; có thể sinh source mới bằng `Filer`.
- **Runtime Reflection:** API đọc runtime-visible metadata của những class đã nạp; không tự quét mọi class trên classpath.
- **Generated index:** lớp Java được sinh chứa **danh sách đã chốt tại lần build**, được dùng như mã Java bình thường.

Nếu runtime cần lấy danh sách bằng `IndexedTypes.names()`, ứng dụng không cần nhìn thấy annotation marker trên class file nữa. Sự khác biệt này thường giúp startup có dữ liệu ổn định hơn runtime scanning, nhưng đổi lại **cần build chạy processor đúng cách mỗi khi tập source thay đổi**.

## 11. Thêm processor vào Maven, Gradle hoặc IDE

Bài chạy bằng CLI và **`-processor` tường minh** để không phụ thuộc cấu hình khám phá tự động. Khi đưa sang build tool:

1. Đặt **annotation API** vào compile classpath của module ứng dụng.
2. Đặt **processor implementation** cùng dependencies vào annotation processor path thích hợp.
3. Đảm bảo build **bật annotation processing** và chọn processor; có thể dùng file dịch vụ `META-INF/services/javax.annotation.processing.Processor` để tự khám phá provider.
4. Đặt generated sources vào output do build tool quản lý, không commit nhầm file tạm nếu dự án không có chính sách commit generated code.
5. Đảm bảo task compile downstream thấy cả source/class do processor tạo.
6. Kiểm tra incremental builds: dạng index **gộp nhiều annotated classes vào một file** thường cần được build tool nhận diện là **aggregating**.

Nếu dùng SPI discovery thay vì `-processor`, file dịch vụ có đường dẫn **chính xác**:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung với ví dụ này:

```text
demo.processor.IndexProcessor
```

File phải nằm ở root classes/JAR của processor path. Tránh lỗi đặt service file vào output **trước khi implementation processor được biên dịch**, rồi compiler cố nạp một provider chưa tồn tại.

**Lưu ý JDK hiện đại:** các JDK mới có thay đổi về cách mặc định bật annotation processing. Cấu hình chọn processor và processor path **tường minh** làm build dễ tái lập hơn. Không chỉ bỏ JAR vào dependency rồi giả định processor sẽ chạy trên mọi JDK/IDE.

## 12. Giới hạn của generator mẫu và cách mở rộng

### 12.1. Nhiều rounds, nhiều processor

`RoundEnvironment` có thể thay đổi qua các rounds. Source do một processor sinh ra có thể được javac đưa vào round kế tiếp. Processor của bài chọn chiến lược **sinh một lần ở round đầu tiên có annotated classes**:

```java
if (roundEnv.processingOver() || generated) {
    return true;
}
```

Cách này tránh tạo trùng, nhưng **không phải giải pháp tổng hợp nhiều round đầy đủ**. Một processor khác sinh `@Indexed class NewComponent` ở round sau sẽ không được thêm vào file `IndexedTypes` của demo.

Nếu yêu cầu mọi phần tử từ nhiều round, hãy thiết kế pipeline tích lũy và tổng hợp có điểm kết thúc thích hợp, có thể cần tách bước tạo index cuối cùng ra một compilation task riêng. Không đợi đến `processingOver()` rồi mới tùy tiện gọi `createSourceFile` cho source cần biên dịch trong cùng compilation: đó là round kết thúc, có thể dẫn đến cảnh báo/lỗi hoặc source không được xử lý như kỳ vọng.

### 12.2. Nhiều module và nguồn ở dependency JAR

`roundEnv.getElementsAnnotatedWith(...)` không có nghĩa processor tự quét toàn bộ mọi class trong mọi dependency của ứng dụng. Nó phản ánh các element mà compiler cung cấp trong quá trình processing cụ thể.

Nếu muốn chỉ mục bao gồm các class từ những module/JAR đã build trước, cần chiến lược hợp nhất metadata liên module, ví dụ mỗi module sinh một index/resource riêng rồi tạo bước tổng hợp sau. Không nên khẳng định một lượt javac trên module hiện tại tự tìm được mọi annotated class của thư viện bên ngoài.

### 12.3. Nested classes và binary name

Ví dụ dùng `TypeElement.getQualifiedName()` rồi lưu tên dạng `demo.app.Alpha`. Với nested class, qualified name có thể là `demo.app.Outer.Inner` nhưng `Class.getName()` dùng `Outer$Inner`.

Nếu mục tiêu là tên phục vụ `Class.forName`, cân nhắc:

```java
String binaryName = processingEnv.getElementUtils()
        .getBinaryName(type)
        .toString();
```

Cần kiểm thử nested class, member class và các vị trí khác được support. Cũng phải quyết định có cho phép class private, abstract, local hoặc anonymous hay không theo hợp đồng công cụ.

### 12.4. Muốn index phương thức hoặc trường

Bài này chỉ nhận `ElementKind.CLASS`, mặc dù một bài toán khác có thể cần index:

- `ExecutableElement` cho method/constructor.
- `VariableElement` cho field, enum constant hoặc parameter.
- `TypeElement` cho class/interface/enum/record.

Muốn làm vậy, `@Target` phải cho phép vị trí tương ứng (như `METHOD`, `FIELD`), và processor phải sinh một cấu trúc đủ định danh vị trí: **class sở hữu, tên member, chữ ký và các đặc điểm overload**. Chỉ lưu tên method dạng `"run"` sẽ không đủ phân biệt overload.

### 12.5. Muốn tạo factory thay vì danh sách string

Trong demo, index chứa `List<String>`, nên chỉ có **metadata tên lớp**. Nếu cần tạo instance, hãy xác định:

- Constructor hoặc factory method nào được phép gọi.
- Class có public/accessible không.
- Các lớp có interface/base type chung không.
- Cần dependency injection/argument gì.
- Có side effect hoặc chi phí khi khởi tạo không.

Không nên phát sinh `new SomeClass()` một cách tùy tiện dựa trên sự hiện diện của `@Indexed`. Annotation chỉ đánh dấu ý định; khả năng khởi tạo và an toàn runtime là các yêu cầu khác.

## 13. Lỗi thường gặp và cách kiểm tra

**Lỗi: Không tìm thấy `demo.generated.IndexedTypes` khi compile.** Kiểm tra javac có thực sự chạy `-processor demo.processor.IndexProcessor`, annotation API trên compile classpath, processor class trên processor path, có ít nhất một class `@Indexed`, và source generated có xuất hiện ở `-s build/generated` hay không.

**Lỗi: `FilerException: Attempt to recreate a file for type ...`.** Processor có thể đã gọi `createSourceFile` hai lần cho cùng qualified name trong cùng một compilation, hoặc có source/file trùng. Giữ một trạng thái `generated` thích hợp và không tự đặt file generated vào source input nếu không có kế hoạch quản lý trùng tên.

**Lỗi: `@Indexed` gắn trên interface mà compile thất bại.** `@Target(TYPE)` cho phép cách gắn này ở mức annotation, nhưng processor cố ý chỉ hỗ trợ `ElementKind.CLASS`. Mở rộng processor nếu thật sự muốn index interface thay vì bỏ qua lỗi.

**Lỗi: Tên lớp sai package.** Không tự ghép tên package bằng chuỗi tùy ý; lấy tên từ `TypeElement` và kiểm tra loại tên cần lưu (qualified name hay binary name).

**Lỗi: Danh sách đổi thứ tự giữa hai lần build.** Đừng dựa vào thứ tự vòng lặp của `Set` từ processor hoặc thứ tự file javac nhận. Trong bài dùng `TreeMap` để sắp theo tên đầy đủ trước khi sinh source.

**Lỗi: Compile thành công nhưng index không cập nhật sau khi xóa annotation.** Kiểm tra incremental build có chạy lại processor và thay thế artifacts cũ không. Với generated aggregator, nên thử clean build trước khi quy lỗi cho `getElementsAnnotatedWith`.

**Lỗi: Processor chạy nhưng không có class generated.** Xem `found.isEmpty()`, `processingOver()`, cờ `generated` và diagnostic `Messager`. Nếu không có annotated classes, demo cố ý không tạo file.

**Lỗi: File generated có nhưng Java không compile được.** Mở file ở `build/generated` và đọc diagnostic javac. Generator phải tạo code Java hợp lệ, escape chuỗi người dùng nhập và xuất dấu ngoặc/dấu phẩy đúng chỗ.

**Lỗi: Compile với `-proc:none`.** Cờ này tắt annotation processing; `IndexedTypes` không được sinh. Khi debug, thử `-processor` tường minh như lệnh ví dụ.

**Lỗi: Dùng Reflection đọc `@Indexed` rồi thấy `null`.** Annotation có retention `SOURCE`, nên đó là hành vi được mong đợi. Hãy dùng index đã sinh, hoặc đổi retention theo nhu cầu Reflection riêng.

## 14. Bài tập thực hành có lời giải định hướng

### Bài 1 — Thay đổi danh sách

Bỏ `@Indexed` khỏi `Beta`, clean output rồi compile lại. Dự đoán `IndexedTypes.names()`.

**Đáp án:** chỉ còn `[demo.app.Alpha]`; `Gamma` vẫn không có marker nên không được index.

### Bài 2 — Kiểm tra thứ tự

Đảo thứ tự source file trong câu lệnh javac: đặt `Beta.java` trước `Alpha.java`. Danh sách có thay đổi không?

**Đáp án:** không theo thiết kế hiện tại. `TreeMap` sắp xếp theo qualified name; `demo.app.Alpha` trước `demo.app.Beta`.

### Bài 3 — Tìm sai kiểu phần tử

Đánh dấu `@Indexed` trên:

```java
@Indexed
interface Plugin {
}
```

Mã có phải được thêm vào index không?

**Đáp án:** không. Processor phát `Diagnostic.Kind.ERROR` vì loại element là `INTERFACE`, khác `ElementKind.CLASS` mà bài demo cho phép.

### Bài 4 — Kiểm tra generated source

Vì sao `IndexedTypes.java` nằm ở `build/generated/demo/generated/` chứ không ở `src/demo/generated/`?

**Đáp án:** `Filer.createSourceFile` dùng qualified name và output do compiler điều khiển, cụ thể `-s build/generated`. Source generated là artifact của quá trình biên dịch, không phải file người dùng phải tạo thủ công.

### Bài 5 — Filer và rounds

Vì sao không nên gọi `createSourceFile("demo.generated.IndexedTypes")` ở mọi round?

**Đáp án:** `Filer` không cho tạo lại cùng file trong một compilation; có thể ném `FilerException`. Cần chiến lược tạo một lần và có thiết kế rõ về phần tử phát hiện qua nhiều rounds.

### Bài 6 — SOURCE retention

`@Indexed` có retention `SOURCE`. Tại sao `App` vẫn truy vấn được danh sách lớp đã được đánh dấu?

**Đáp án:** `App` gọi **lớp chỉ mục `IndexedTypes` do compiler sinh và biên dịch**, không gọi Reflection để lấy annotation. Dữ liệu danh sách đã được chốt trong generated source.

### Bài 7 — Mở rộng tên kiểu lồng

Giả sử đánh dấu `@Indexed` lên `Outer.Inner`. Vì sao cần suy nghĩ về `getQualifiedName` và `getBinaryName` nếu muốn dùng `Class.forName`?

**Đáp án:** tên nguồn và binary name của nested class có thể khác nhau (`Outer.Inner` so với `Outer$Inner`). Tên lưu trong chỉ mục phải phù hợp với API tiêu thụ.

### Bài 8 — Thiết kế index cho method

Nếu đánh dấu nhiều method overload bằng một annotation mới, chỉ lưu `getSimpleName()` của `ExecutableElement` có đủ không?

**Đáp án:** không. Cần thêm class sở hữu và chữ ký parameter/return type thích hợp để phân biệt overload và định danh method chính xác.

## 15. Checklist hoàn thành bài tập

1. Annotation `@Indexed` có `@Target` và `@Retention` phù hợp mục tiêu compile-time?
2. Processor được biên dịch trước và được javac chọn bằng `-processor` hoặc service discovery đúng?
3. `@SupportedAnnotationTypes` dùng đúng tên `demo.marker.Indexed`?
4. `RoundEnvironment` tìm được đúng những phần tử được đánh dấu trong lượt compile?
5. Đã chọn và kiểm tra `ElementKind` hỗ trợ?
6. Đã lấy tên từ `TypeElement` thay vì cố dùng runtime class loading?
7. Có quy tắc sort/deduplicate ổn định, để output không phụ thuộc thứ tự duyệt?
8. `Filer.createSourceFile` được gọi đúng một lần cho một qualified generated class?
9. Writer được đóng bằng try-with-resources?
10. `-s` chỉ tới thư mục generated sources, `-d` chỉ tới compiled classes?
11. Có thể xem và compile file `IndexedTypes.java` đã sinh?
12. App có dùng danh sách mà không cần quét runtime classpath?
13. Test đã kiểm tra có `Alpha`, `Beta` và không có `Gamma`?
14. Có kiểm tra thay đổi annotation bằng clean build?
15. Có phân biệt giới hạn single-round demo với bài toán aggregating nhiều rounds/nhiều module?
16. Nếu build thất bại, có đọc diagnostic thay vì che lỗi hoặc ghi đè file generated?

**Kết luận:** một annotation processor dùng `RoundEnvironment` để tìm những `Element` được đánh dấu, `TypeElement` để lấy tên kiểu và `Filer.createSourceFile` để tạo **một lớp chỉ mục Java có thể biên dịch**. Bài demo sinh `demo.generated.IndexedTypes` từ hai class `@Indexed`, đảm bảo thứ tự ổn định và cho ứng dụng đọc danh sách bằng `IndexedTypes.names()` mà không cần Reflection runtime. Đây là nền tảng để phát triển các công cụ compile-time registration, source generation và static metadata indexing, miễn là mở rộng có chủ đích cho nhiều rounds, các kiểu element khác và cấu hình build thực tế.