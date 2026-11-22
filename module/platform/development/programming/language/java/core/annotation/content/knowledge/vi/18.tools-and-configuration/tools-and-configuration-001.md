# Đăng ký annotation processor bằng META-INF/services/javax.annotation.processing.Processor

**Annotation processor** là một chương trình chạy **trong quá trình biên dịch Java**, có thể kiểm tra metadata, phát lỗi/cảnh báo hoặc sinh source. Theo API JSR 269, một processor triển khai `javax.annotation.processing.Processor`; thông thường ta kế thừa `AbstractProcessor` rồi viết `process(...)`.

Muốn `javac` **tự tìm** processor trong artifact mà không phải chỉ định FQCN bằng `-processor` mỗi lần, có thể dùng Java **Service Provider Interface (SPI)**. Cấu hình SPI có một đường dẫn đặc biệt, tính từ **gốc classpath/JAR processor**:

```text
META-INF/services/javax.annotation.processing.Processor
```

File văn bản này chứa **tên lớp đầy đủ của implementation**:

```text
tutorial.processing.InspectProcessor
```

Tên **file** là FQCN của **service interface** `javax.annotation.processing.Processor`; nội dung **file** là FQCN của **provider class** mà bạn tự viết. Hai tên khác nhau và không được tráo đổi.

Để processor được gọi, chỉ đặt file dịch vụ thôi là **chưa đủ**: lớp implementation phải nạp được, artifact phải nằm ở đúng đường dẫn tìm processor và annotation processing phải được bật theo cấu hình của `javac`/build tool. Bài này hướng dẫn đầy đủ một ví dụ Java 17+, kiểm chứng kết quả thực tế, đóng gói JAR và xử lý lỗi.

## 1. Vị trí của SPI trong quy trình biên dịch

Giả sử có lớp:

```java
@Inspect("catalog")
public class Catalog {
}
```

Bạn muốn compiler ghi nhận những lớp gắn `@Inspect`. Ba thành phần thực hiện việc đó là:

| Thành phần | Chức năng |
| --- | --- |
| `Inspect` | Định nghĩa loại annotation, dữ liệu metadata của source |
| `InspectProcessor` | Code Java được compiler gọi để xử lý `@Inspect` |
| `META-INF/services/javax.annotation.processing.Processor` | Khai báo implementation nào có thể được khám phá qua SPI |

Compiler hoạt động theo luồng:

```text
Source code Catalog.java có @Inspect("catalog")
                  |
                  v
       javac được bật annotation processing
                  |
                  v
  Tìm SPI trên processor path
  META-INF/services/javax.annotation.processing.Processor
                  |
                  v
  Đọc provider: tutorial.processing.InspectProcessor
                  |
                  v
  Load + khởi tạo implementation Processor
                  |
                  v
  Đưa RoundEnvironment vào process(...)
                  |
                  v
  InspectProcessor phát NOTE hoặc xử lý metadata
                  |
                  v
  Compiler tiếp tục biên dịch/sinh file theo chế độ đã chọn
```

**Mấu chốt:** đây là plugin của **compiler**, không phải callback mà JVM tự gọi khi ứng dụng khởi động. `@Inspect` không tự làm điều gì nếu không có processor/consumer.

## 2. Cấu trúc project mẫu

Để thử mà không cần Maven hay Gradle, đặt các file như sau:

```text
spi-demo/
├── src/
│   ├── processor/
│   │   └── tutorial/
│   │       ├── annotations/
│   │       │   └── Inspect.java
│   │       └── processing/
│   │           └── InspectProcessor.java
│   └── app/
│       └── tutorial/
│           └── app/
│               └── Catalog.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── javax.annotation.processing.Processor
└── build/  (được tạo bằng lệnh biên dịch)
    ├── processor/
    └── app/
```

Tên các package là ví dụ cụ thể. Bạn có thể thay đổi chúng nhưng phải cập nhật đồng bộ `package`, `import`, `@SupportedAnnotationTypes` và nội dung file dịch vụ.

`resources/` chỉ là thư mục nguồn chứa tài nguyên. **Java compiler không tự tìm SPI ở một đường dẫn tùy ý trong source tree**. Trong ví dụ ta sẽ biên dịch processor vào `build/processor`, sau đó copy `META-INF/` tới **gốc** `build/processor`.

Cấu trúc đích đúng:

```text
build/processor/
├── tutorial/
│   ├── annotations/
│   │   └── Inspect.class
│   └── processing/
│       └── InspectProcessor.class
└── META-INF/
    └── services/
        └── javax.annotation.processing.Processor
```

Nếu nén thành JAR, các đường dẫn này phải là **entries bên trong JAR**, không chứa thêm tiền tố `build/processor/`.

## 3. Inspect.java — khai báo annotation mà processor đọc

File **`src/processor/tutorial/annotations/Inspect.java`**:

```java
package tutorial.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Inspect {
    String value();
}
```

Vì `@Target(TYPE)`, annotation này gắn trên khai báo kiểu như `class`. Phần tử `String value()` cho phép viết dạng ngắn `@Inspect("catalog")` thay cho `@Inspect(value = "catalog")`.

Vì retention là `SOURCE`, compiler xử lý metadata lúc compile nhưng không giữ lần sử dụng vào class file để Java Reflection truy vấn sau đó. **Processor không yêu cầu retention `RUNTIME`**: annotation processor đọc mô hình source/class do javac cung cấp.

Điều quan trọng nhất là processor được chạy **ngay khi biên dịch file có annotation**. Thay retention thành `RUNTIME` không tự sửa được lỗi processor chưa được khám phá.

## 4. InspectProcessor.java — triển khai Processor

File **`src/processor/tutorial/processing/InspectProcessor.java`**:

```java
package tutorial.processing;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import tutorial.annotations.Inspect;

@SupportedAnnotationTypes("tutorial.annotations.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class InspectProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Inspect.class)) {

            Inspect inspect = element.getAnnotation(Inspect.class);

            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "InspectProcessor: " + element.getSimpleName()
                            + " -> " + inspect.value());
        }

        return true;
    }
}
```

`AbstractProcessor` triển khai interface `javax.annotation.processing.Processor` và cung cấp cơ sở cho các phương thức của processor. Do đó `InspectProcessor` là một **service provider** hợp lệ khi được khai báo public và có thể khởi tạo (trong ví dụ, lớp public không tự viết constructor nên có constructor không tham số public).

Ý nghĩa các thành phần:

- `@SupportedAnnotationTypes("tutorial.annotations.Inspect")` dùng **FQCN của annotation muốn xử lý**, **không phải** tên processor.
- `@SupportedSourceVersion(RELEASE_17)` cho biết source level mà processor hỗ trợ trong ví dụ.
- `RoundEnvironment.getElementsAnnotatedWith(Inspect.class)` lấy các phần tử được compiler cung cấp cho round có `@Inspect`.
- `element.getAnnotation(Inspect.class)` lấy metadata dễ đọc vì `Inspect` chỉ chứa chuỗi `String`.
- `Messager.printMessage(Diagnostic.Kind.NOTE, ...)` phát **compiler diagnostic**, thường hiện trong output của `javac`.
- `return true` nghĩa là processor **claim loại annotation được hỗ trợ** ở round đó, không phải mã trả về báo build thành công hay thất bại.

Trong processor có nhiều dữ liệu phức tạp như class literals, enum, annotations lồng hoặc mảng, nên cân nhắc `AnnotationMirror`/`AnnotationValue` và `TypeMirror`, tránh giả định mọi kiểu trong source đã được JVM tải thành `Class<?>`.

**Processor có thể chạy nhiều round.** Ví dụ không sinh source và chỉ phát note khi có phần tử phù hợp; không suy ra rằng processor trong mọi dự án chỉ được gọi đúng một lần.

## 5. Catalog.java — class được processor kiểm tra

File **`src/app/tutorial/app/Catalog.java`**:

```java
package tutorial.app;

import tutorial.annotations.Inspect;

@Inspect("catalog")
public class Catalog {
}
```

`Catalog` không cần `main`. Khi compiler xử lý nó, `InspectProcessor` phát thông báo chứa `Catalog` và giá trị `"catalog"`.

Bạn **không** cần chạy `java tutorial.app.Catalog`. Processor thuộc build/compile time, không phải lifecycle của đối tượng `Catalog`.

## 6. File dịch vụ đúng tên, đúng nội dung

Tạo file tại đường dẫn nguồn:

`resources/META-INF/services/javax.annotation.processing.Processor`

Nội dung chính xác của ví dụ:

```text
tutorial.processing.InspectProcessor
```

Các quy tắc SPI cần nhớ:

1. **Tên file là service interface** `javax.annotation.processing.Processor`, không phải `InspectProcessor`, `Inspect.java` hoặc tên package ứng dụng.
2. **Mỗi dòng ghi một provider FQCN**. Đối với ví dụ, provider là `tutorial.processing.InspectProcessor`.
3. **Không ghi đường dẫn filesystem** như `tutorial/processing/InspectProcessor.class` và không thêm `.class` hay `.java`.
4. **Vị trí phải đúng**: `META-INF/services` ở gốc một mục trên processor path, ví dụ gốc directory classes hoặc gốc JAR.
5. **Nên lưu UTF-8 không BOM**, tránh ký tự lạ trước tên lớp. SPI service configuration cho phép bỏ qua dòng trống và dòng comment bắt đầu bằng `#`.
6. **Nhiều providers:** có thể ghi nhiều dòng FQCN, nhưng từng class phải tồn tại, load được, triển khai `Processor`, và có thể tạo instance hợp lệ.
7. **Phân biệt extension:** tên file kết thúc ở `.Processor`, không được vô tình lưu thành `.Processor.txt`.

Ví dụ nội dung cho **hai providers chỉ khi cả hai lớp thật sự tồn tại**:

```text
tutorial.processing.InspectProcessor
tutorial.processing.AuditProcessor
```

Trong bài chạy thực tế chỉ sử dụng một provider `InspectProcessor`. Dòng `AuditProcessor` ở đây chỉ minh họa khả năng đăng ký nhiều implementation.

### Provider phải được nạp được

File dịch vụ không chứa bytecode. Nếu có file SPI nhưng lớp `InspectProcessor.class` không nằm trên processor path, hoặc provider không phải lớp triển khai `Processor`, sẽ gặp lỗi service loading. Ví dụ thông báo có thể chứa:

```text
Bad service configuration file, or exception thrown while constructing Processor object
Provider tutorial.processing.InspectProcessor not found
```

Đây là **ví dụ hình thức lỗi thường gặp**, không khẳng định mọi JDK in nguyên xi hai dòng. Điều cần kiểm tra là **file dịch vụ** và **lớp provider/dependencies** có tồn tại đúng cấu trúc ở path mà compiler đang dùng hay không.

## 7. Biên dịch ví dụ theo thứ tự tránh lỗi tự khám phá sớm

Đặt terminal ở gốc thư mục `spi-demo`. Trên Linux/macOS (Bash), tạo output:

```bash
mkdir -p build/processor build/app
```

**Bước 1 — Biên dịch annotation API và processor implementation:**

```bash
javac --release 17 -d build/processor \
  src/processor/tutorial/annotations/Inspect.java \
  src/processor/tutorial/processing/InspectProcessor.java
```

Sau lệnh này, `build/processor/tutorial/...` chứa `Inspect.class` và `InspectProcessor.class`.

**Bước 2 — Copy service file đến gốc processor output:**

```bash
cp -R resources/META-INF build/processor/
```

Kiểm tra tồn tại:

```text
build/processor/META-INF/services/javax.annotation.processing.Processor
```

**Bước 3 — Biên dịch Catalog.java, yêu cầu processor discovery:**

```bash
javac --release 17 -proc:full \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app \
  src/app/tutorial/app/Catalog.java
```

Khi processor chạy, compiler in diagnostic:

```text
Note: InspectProcessor: Catalog -> catalog
```

Dòng này có thể ở stderr của `javac`, nhưng không phải lỗi compiler và không phải output của chương trình `Catalog` khi chạy. Với compiler/IDE khác nhau, format hoặc vị trí hiển thị diagnostic có thể khác.

**Vì sao không copy SPI vào `build/processor` trước bước 1?** Trong quá trình compiler tự khám phá processor, nó có thể đọc service file **trước khi implementation class được biên dịch**. Nếu file tham chiếu đến provider chưa tồn tại, sẽ có lỗi service configuration. Để tránh vòng lặp khó hiểu, biên dịch implementation trước, sau đó mới đặt resource SPI và biên dịch consumer.

### PowerShell trên Windows

Các lệnh tương đương có thể viết **mỗi lệnh trên một dòng** (không phụ thuộc ký hiệu nối dòng của Bash):

```powershell
New-Item -ItemType Directory -Force build/processor, build/app | Out-Null
javac --release 17 -d build/processor src/processor/tutorial/annotations/Inspect.java src/processor/tutorial/processing/InspectProcessor.java
Copy-Item -Recurse resources/META-INF build/processor/
javac --release 17 -proc:full -cp build/processor -processorpath build/processor -d build/app src/app/tutorial/app/Catalog.java
```

Dù shell có khác, đường dẫn trong output/JAR và tên service file vẫn giống về cấu trúc. Ví dụ này không cần Maven, Gradle hay plugin bên ngoài.

**Đã kiểm chứng với JDK:** processor source biên dịch thành công với `javac --release 17`. Lượt biên dịch consumer dùng SPI và `-proc:full` gọi processor, phát diagnostic `Note: InspectProcessor: Catalog -> catalog`.

## 8. Ba loại đường dẫn và các tùy chọn compiler

Lệnh chính:

```bash
javac --release 17 -proc:full \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app \
  src/app/tutorial/app/Catalog.java
```

Cần tách rõ:

| Tham số | Vai trò |
| --- | --- |
| `--release 17` | Source/API/bytecode mục tiêu Java 17 |
| `-cp build/processor` | **Compile classpath** để source `Catalog` tìm được `tutorial.annotations.Inspect` |
| `-processorpath build/processor` | **Processor path** để javac tìm và nạp processor + service configuration |
| `-proc:full` | Bật processing và tiếp tục biên dịch class output |
| `-d build/app` | Nơi sinh class files của ứng dụng |

Trong ví dụ, `build/processor` chứa cả annotation API và processor, nên hai đường dẫn `-cp` và `-processorpath` cùng một thư mục. Điều đó **không có nghĩa hai tùy chọn là tương đương**.

Ở dự án thực tế, annotation API và processor implementation có thể nằm ở **hai artifact**: API trên compile classpath và implementation cùng dependencies trên annotation processor path. Nếu processor nằm trên classpath của ứng dụng nhưng không trên path mà compiler dùng để tìm processors, code có thể compile vẫn không chạy processor.

### Java 23+ và việc tự khởi chạy processor

Các JDK gần đây thay đổi chính sách liên quan đến annotation processing mặc định, đặc biệt khi nâng cấp từ phiên bản cũ lên **JDK 23 trở lên**. Một build trước đây chỉ dựa vào việc processor xuất hiện ngẫu nhiên trên classpath không nên giả định compiler sẽ luôn tự chạy nó.

Chủ động yêu cầu xử lý bằng `-proc:full`, hoặc khai báo processor và processor path theo cơ chế của build tool, giúp ý định rõ ràng và việc biên dịch tái lập được. Đồng thời giữ processor path gọn và tin cậy vì processor là **code có thể chạy trong quá trình build**.

## 9. SPI discovery khác gì -processor và -proc:none?

### 9.1. Dùng service file để khám phá

```bash
javac --release 17 -proc:full \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

Không có tùy chọn `-processor`. Javac có thể khám phá provider từ `META-INF/services/javax.annotation.processing.Processor` trên processor path.

### 9.2. Chỉ định implementation trực tiếp

```bash
javac --release 17 \
  -processor tutorial.processing.InspectProcessor \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

` -processor` truyền FQCN processor muốn chạy. Cách này **không cần dựa vào file service** để tìm tên provider nếu class nạp được trên đường dẫn tương ứng.

Đây là phép thử rất hữu ích: nếu `-processor tutorial.processing.InspectProcessor` chạy được nhưng discovery không chạy, khả năng cao nên kiểm tra **vị trí/nội dung SPI file**, artifact và processor path trước tiên.

### 9.3. Tắt annotation processing

```bash
javac --release 17 -proc:none \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

Processor không được chạy. `Catalog.java` vẫn có thể biên dịch thành `Catalog.class` nếu source/dependencies hợp lệ, nhưng **không xuất hiện note từ `InspectProcessor`**.

### 9.4. Chạy processor mà không thực hiện compile class thông thường

```bash
javac --release 17 -proc:only \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

` -proc:only` dùng khi muốn xử lý annotation mà không tiếp tục toàn bộ quá trình tạo class files thông thường cho source. Nó thích hợp cho một số bước chẩn đoán/generate source nhưng **không tương đương một build ứng dụng đầy đủ**.

### Bảng so sánh

| Cách gọi compiler | Có gọi processor trong ví dụ? | Vai trò file SPI |
| --- | --- | --- |
| `-proc:full -processorpath ...` | Có | Compiler tìm provider từ SPI |
| `-processor tutorial.processing.InspectProcessor` | Có | Không cần để chỉ định tên processor |
| `-proc:none` | Không | Bị bỏ qua vì processing tắt |
| `-proc:only -processorpath ...` | Có | Có thể dùng để khám phá processor |

**Kiểm thử thực tế:** cả ba đường chính đã được chạy với `javac --release 17`: discovery có `-proc:full` phát note, `-proc:none` không phát note, và chỉ định `-processor` phát note khi class implementation được tìm thấy. Kết quả compile đều thành công.

## 10. Đóng gói processor thành JAR

Từ ví dụ ở mục 7, sau khi đã biên dịch processor **và copy `META-INF/services`** vào `build/processor`, có thể đóng gói:

```bash
jar --create --file build/inspect-processor.jar -C build/processor .
```

Kiểm tra các entry:

```bash
jar --list --file build/inspect-processor.jar
```

Bạn cần nhìn thấy tối thiểu:

```text
META-INF/services/javax.annotation.processing.Processor
tutorial/processing/InspectProcessor.class
tutorial/annotations/Inspect.class
```

Đây là **các entry quan trọng phải hiện diện**, không phải bản chép toàn bộ output của `jar --list`. Archive có thể còn có `META-INF/MANIFEST.MF`, thư mục package và các entry khác.

Khi dùng JAR vừa tạo:

```bash
javac --release 17 -proc:full \
  -cp build/inspect-processor.jar \
  -processorpath build/inspect-processor.jar \
  -d build/app src/app/tutorial/app/Catalog.java
```

Ở demo này JAR chứa cả annotation API và implementation; trong dự án production có thể tách hai artifact cho rõ vai trò.

**Lỗi phổ biến:** lưu nguyên đường dẫn `resources/META-INF/services/...` **bên trong JAR** thay vì chỉ `META-INF/services/...`. Trình tìm kiếm provider không đi đoán thêm folder `resources`. Quy tắc là **service file phải ở gốc archive** theo chuẩn SPI.

## 11. Đăng ký bằng build tool

Trong Maven/Gradle, nhiệm vụ copy resource thường do cơ chế resource processing của plugin/source set thực hiện. Nhưng bạn vẫn cần kiểm tra **artifact đầu ra** chứ không chỉ nhìn source tree.

Các nguyên tắc áp dụng như nhau:

- **Processor JAR** thực sự chứa `META-INF/services/javax.annotation.processing.Processor`.
- Dependency chứa implementation processor được đưa vào **annotation processor path**, không chỉ `runtimeClasspath`.
- Source code được biên dịch nhìn thấy annotation API qua **compile classpath**.
- Annotation processing được bật/được yêu cầu theo cách phù hợp với JDK/plugin.
- Nếu processor cần thư viện phụ trợ, dependencies đó phải nạp được bởi processor class loader.
- Compiler đang được build tool/IDE sử dụng phải tương thích với phiên bản processor.
- Khi nghi ngờ build tool, dùng ví dụ CLI `javac` để phân biệt lỗi class/processor với lỗi cấu hình build.

Một IDE có thể hiển thị `@Inspect` và code completion tốt nhưng processor không chạy ở thời điểm build nếu annotation processing đã bị tắt. Ngược lại, annotation processing có thể chạy bằng một task riêng mà không in output ở terminal bạn đang theo dõi. Đừng đánh đồng **phân tích source trong editor** với **thực thi JSR269 processor**.

## 12. Dò lỗi bằng -XprintRounds và -XprintProcessorInfo

Javac cung cấp thêm các tùy chọn chẩn đoán:

```bash
javac --release 17 -proc:full \
  -XprintRounds -XprintProcessorInfo \
  -cp build/processor \
  -processorpath build/processor \
  -d build/app src/app/tutorial/app/Catalog.java
```

- `-XprintRounds` giúp xem các **processing rounds**.
- `-XprintProcessorInfo` giúp quan sát processor được compiler gọi cùng thông tin về annotation types.
- `Diagnostic.Kind.NOTE` từ processor giúp phân biệt việc `process` có được gọi với việc chỉ tạo ra `Catalog.class`.

Không dựa vào output `-X...` như một API dữ liệu ổn định giữa các JDK; chúng phục vụ chẩn đoán. Khi lập trình processor để báo lỗi thực sự, dùng `Messager.printMessage(Diagnostic.Kind.ERROR, ..., element)` hoặc overload phù hợp để gắn lỗi với vị trí source.

## 13. Mười lỗi cấu hình thường gặp

### 13.1. File SPI sai tên

**Sai:**

```text
META-INF/services/InspectProcessor
META-INF/services/tutorial.processing.InspectProcessor
META-INF/services/javax.annotation.processing.Processor.txt
```

**Đúng:**

```text
META-INF/services/javax.annotation.processing.Processor
```

Tên file chính là service interface. Không đặt tên file theo annotation type hoặc implementation class.

### 13.2. Nội dung SPI không phải FQCN

**Sai:**

```text
InspectProcessor
tutorial/processing/InspectProcessor.class
tutorial.processing.InspectProcessor.java
```

**Đúng:**

```text
tutorial.processing.InspectProcessor
```

Nhớ đối chiếu package declaration trong `InspectProcessor.java`.

### 13.3. Resource không vào artifact

Bạn tạo file đúng ở source nhưng quên copy, hoặc plugin đóng gói file ở sai folder. Kiểm tra `jar --list` và tìm chính xác entry `META-INF/services/javax.annotation.processing.Processor`.

### 13.4. Provider class chưa tồn tại

Compiler tìm thấy file SPI nhưng không tìm được class provider do chưa biên dịch, compile lỗi hoặc JAR không đóng gói class. Biên dịch processor trước, copy resource sau. Kiểm tra đúng entry `tutorial/processing/InspectProcessor.class` trong output/JAR.

### 13.5. Implementation không đúng interface hoặc không thể khởi tạo

Provider phải triển khai `javax.annotation.processing.Processor` và nạp/khởi tạo được. Lớp không public, thiếu constructor phù hợp, abstract hoặc phụ thuộc vắng có thể khiến service loading thất bại.

### 13.6. Nhầm compile classpath với processor path

`Catalog` thấy annotation API nhưng processor implementation không nằm trên `-processorpath`, do đó không có provider để compiler chạy. Thiết lập đúng cả hai, kể cả dependencies mà provider cần.

### 13.7. Annotation processing không được bật

` -proc:none` tắt processing. Khi nâng JDK hoặc đổi build tool, đừng giả định processor bất kỳ trên classpath được tự khởi chạy. Dùng `-proc:full` hoặc cách chọn processor được hỗ trợ phù hợp.

### 13.8. @SupportedAnnotationTypes sai

`@SupportedAnnotationTypes("tutorial.annotations.Inspect")` phải ghi đúng loại annotation. Ghi `"InspectProcessor"` hoặc tên không có package sẽ không đăng ký đúng annotation mong muốn trong ví dụ này.

### 13.9. Có provider nhưng không có annotated element trong round

Processor có thể được nạp nhưng không tìm thấy `@Inspect` trên những element mà javac đưa vào vòng xử lý. Kiểm tra đúng source được compile, annotation type/package, `RoundEnvironment` và các processing rounds; chú ý code có thể sinh thêm source qua nhiều vòng.

### 13.10. Nhầm lỗi retention với lỗi SPI

`@Retention(SOURCE)` không ngăn processor xử lý annotation khi compile. `@Retention(RUNTIME)` cũng không khiến javac tự khởi chạy processor. Retention quy định **lưu metadata qua các giai đoạn**, còn service registration quy định **cách tìm implementation của processor**.

## 14. Đăng ký SPI trong hệ thống Java Module

Các lệnh chính của bài dựa vào **classpath và processor path**. Nếu đưa processor vào **named Java module**, Java Platform Module System (JPMS) còn hỗ trợ khai báo provider ở `module-info.java`:

```java
module tutorial.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with tutorial.processing.InspectProcessor;
}
```

Đoạn trên là **minh họa cơ chế cung cấp service của module**, không phải một `module-info.java` hoàn chỉnh cho project demo classpath. Nếu chia annotation API và processor thành modules khác nhau, bạn cần thiết kế `requires`/`exports` thích hợp.

Khái niệm cần phân biệt:

- `META-INF/services/javax.annotation.processing.Processor` là cách đăng ký provider trong hệ sinh thái **JAR/classpath SPI**.
- `provides ... with ...` là cú pháp đăng ký dịch vụ của named module.
- `--processor-module-path` có cơ chế tìm processor theo module path, khác với `-processorpath`.
- Không mặc định file SPI truyền thống thay thế mọi khai báo `provides` khi đang sử dụng named-module resolution.

Bài học hiện tại sử dụng cách phổ biến và đơn giản: **classpath/processor path + META-INF/services**.

## 15. Quyền thực thi và tính an toàn build

Annotation processor là **mã chạy trên máy build trong tiến trình công cụ biên dịch**, không chỉ là metadata vô hại. Khi compiler khám phá provider từ dependency, nó có thể tải và chạy code trong processor trong lúc build.

Do đó:

1. Chỉ dùng processor artifact từ nguồn đáng tin; kiểm soát version giống dependency build quan trọng khác.
2. Không vô ý để JAR không tin cậy vào processor path.
3. Cấu hình processor path **tường minh và tái lập được** trên máy developer/CI.
4. Hiểu processor có thể đọc source, phát diagnostic, tạo file thông qua `Filer`, và thường chạy trong nhiều round.
5. Đừng giả định `SOURCE` retention là biện pháp hạn chế quyền của processor; retention không sandbox code.
6. Khi processor sinh source, xác định rõ thư mục output và điều kiện tránh sinh trùng file.
7. Dùng `Messager` và các API mô hình ngôn ngữ để phát lỗi chính xác, tránh tự ý sửa source người dùng.
8. Kiểm tra task compile và JDK đang dùng trên CI, vì nâng JDK có thể thay đổi lựa chọn mặc định về processing.

Một cấu hình SPI đúng về cú pháp không chứng minh mọi processor đều an toàn; chính code provider và dependency của nó phải được quản lý.

## 16. Bài tập tự kiểm tra

### Bài 1 — Tên file và nội dung

Bạn viết processor `com.example.tools.CheckProcessor`. File SPI phải tên gì và chứa dòng gì?

**Đáp án:** file `META-INF/services/javax.annotation.processing.Processor`, nội dung `com.example.tools.CheckProcessor`.

### Bài 2 — Có class nhưng thiếu SPI

JAR đã có `InspectProcessor.class` nhưng không chứa `META-INF/services/javax.annotation.processing.Processor`. Nếu không có `-processor`, cách service discovery trong bài có tự tìm tên provider từ class đó không?

**Đáp án:** không. Cần khai báo provider đúng trong service file, hoặc dùng `-processor` để chỉ định implementation.

### Bài 3 — App compile được nhưng thiếu NOTE

`Catalog.class` được tạo, nhưng không có dòng `Note: InspectProcessor: Catalog -> catalog`. Hãy liệt kê ba nguyên nhân.

**Gợi ý:** annotation processing bị tắt; JAR trên compile classpath nhưng không được đưa vào processor path; resource SPI sai/thiếu; `@SupportedAnnotationTypes` khai báo sai; processor không load được.

### Bài 4 — SOURCE retention

Vì sao `@Inspect` có retention `SOURCE` vẫn được processor nhìn thấy khi compile nhưng không đọc được bằng Reflection sau khi build?

**Đáp án:** annotation processor xử lý metadata trong mô hình biên dịch; `SOURCE` không giữ lần sử dụng annotation đến class file/runtime.

### Bài 5 — Kiểm tra jar

Sau khi đóng gói processor JAR, dùng lệnh nào để biết file SPI có thật sự ở đúng root archive?

**Đáp án:** `jar --list --file build/inspect-processor.jar`. Kiểm tra entry `META-INF/services/javax.annotation.processing.Processor`.

### Bài 6 — Chỉ định tường minh

Lệnh với `-processor tutorial.processing.InspectProcessor` chạy được nhưng lệnh `-proc:full` dựa vào discovery không chạy. Nên kiểm tra gì trước tiên?

**Đáp án:** file dịch vụ, nội dung provider FQCN, resource đóng gói, processor path và chế độ chọn processor. Implementation đã có bằng chứng chạy được khi chỉ định trực tiếp.

### Bài 7 — Tắt processor

Thêm `-proc:none` vào lần compile ứng dụng; có còn NOTE do processor tạo ra không?

**Đáp án:** không. Compiler không chạy processors khi processing bị tắt, dù `Catalog` vẫn có thể compile nếu code hợp lệ.

### Bài 8 — Nhiều providers

File SPI có hai FQCN nhưng một provider không tồn tại. Vì sao đây không phải cách hợp lệ để đăng ký một processor “để dành”?

**Đáp án:** service loader có thể cố load mọi provider được liệt kê và lỗi với provider không tồn tại. Chỉ khai báo những implementation thực sự có trong artifact/path.

## 17. Checklist cuối cùng

1. `InspectProcessor` là lớp public triển khai `Processor` (trực tiếp hoặc qua `AbstractProcessor`) và khởi tạo được.
2. `@SupportedAnnotationTypes` khai báo chính xác annotation type mà processor hỗ trợ.
3. File SPI có tên đúng **`META-INF/services/javax.annotation.processing.Processor`**.
4. Dòng trong file SPI là **FQCN lớp provider**, không phải tên annotation, path hay tên JAR.
5. File SPI được copy/đóng gói ở **gốc output/JAR**, không bị giữ ở thư mục `resources` bên trong archive.
6. Processor class và dependencies có trên processor path.
7. Source ứng dụng nhìn thấy annotation API qua compile classpath.
8. Annotation processing được bật bằng cách chọn processor hoặc `-proc:full` khi phù hợp.
9. CLI `javac` gọi processor và phát diagnostic mong đợi.
10. `-proc:none` tắt được processing để thử phân biệt lỗi.
11. `jar --list` xác nhận service file và class implementation trong artifact.
12. Build tool/IDE/CI dùng đúng JDK và cấu hình processor, không dựa vào giả định tự động từ classpath.
13. Nếu dùng JPMS, xem xét riêng `module-info.java` và processor module path.
14. Processor artifact được kiểm soát bảo mật vì đây là code chạy lúc build.

**Kết luận:** muốn đăng ký annotation processor theo Java SPI, **đặt file `META-INF/services/javax.annotation.processing.Processor` trong gốc processor output/JAR**, ghi FQCN của provider triển khai `Processor`, để compiler tải được provider trên processor path và **chủ động bật annotation processing**. `@SupportedAnnotationTypes` điều khiển loại annotation mà processor xử lý; file dịch vụ điều khiển **cách tìm processor**, còn `-processor` cho phép chỉ định tường minh để kiểm tra/debug.