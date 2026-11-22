# Liên hệ `--release`, `SourceVersion` và tính tương thích JDK trong annotation processing

## 1. Ba phiên bản cần tách biệt

Khi biên dịch một dự án có **annotation processor**, ít nhất ba câu hỏi về phiên bản thường xuất hiện:

1. **JDK nào đang chạy `javac` và processor?** Đây là *host JDK*: công cụ biên dịch và JVM thực thi mã của processor.
2. **Mã ứng dụng cần tương thích với Java phiên bản nào?** Tùy chọn `javac --release N` đặt phạm vi ngôn ngữ, API nền tảng và định dạng class file mà mã ứng dụng được biên dịch hướng tới.
3. **Processor công bố hiểu nguồn Java đến mức nào?** `javax.lang.model.SourceVersion`, dùng qua `@SupportedSourceVersion` hoặc `getSupportedSourceVersion()`, mô tả khả năng xử lý mô hình nguồn của processor.

Ba thông tin này **liên quan nhưng không tương đương**.

Ví dụ, sử dụng **JDK 21 để chạy `javac`**, biên dịch **mã ứng dụng hướng tới Java 17** với `--release 17`, và dùng processor có `@SupportedSourceVersion(SourceVersion.RELEASE_17)` là một cấu hình hợp lý. **Không** cần host JDK phải là đúng 17, miễn `javac` được dùng hỗ trợ `--release 17` và processor cùng các dependency của nó chạy được trên host JDK.

Sơ đồ:

```text
Host JDK (ví dụ JDK 21)
  ├── Chạy javac
  ├── Chạy annotation processor bằng JVM của quá trình biên dịch
  │      └── Processor công bố SourceVersion.RELEASE_17
  │          (khả năng xử lý source, không cấu hình bytecode đầu ra)
  └── javac --release 17 để biên dịch ứng dụng
         ├── Quy tắc ngôn ngữ Java 17
         ├── API nền tảng tương ứng Java 17
         └── Class file phiên bản Java 17 (major version 61)
                     │
                     v
            Môi trường Java 17+ có thể nạp class file
            nếu dependency và những điều kiện runtime khác phù hợp
```

Bài này phân biệt **tương thích source**, **tương thích API**, **tương thích bytecode** và **khả năng chạy processor** để tránh trường hợp “biên dịch thành công ở máy lập trình nhưng không chạy được ở máy triển khai”.

## 2. `javac --release N` làm gì?

Tùy chọn:

```bash
javac --release 17 Example.java
```

yêu cầu compiler nhắm tới một bản phát hành Java được hỗ trợ, gồm các phần quan trọng:

| Khía cạnh | Tác dụng của `--release 17` |
| --- | --- |
| **Cú pháp và đặc tính ngôn ngữ** | Chỉ cho phép các tính năng Java phù hợp với release 17, không tự bật cú pháp của những release mới hơn |
| **API nền tảng JDK** | Giới hạn việc biên dịch theo các API Java SE/Java Platform có trong bản release đích do `javac` cung cấp |
| **Định dạng class file** | Sinh class file có mức phiên bản tương ứng Java 17, tức **major version 61** |

Nếu chương trình sử dụng API nền tảng xuất hiện lần đầu ở Java 21, biên dịch bằng JDK mới với `--release 17` không được phép coi API đó là có sẵn ở Java 17.

Tương tự, nếu dùng cú pháp ngôn ngữ chỉ được giới thiệu ở release mới hơn 17, `--release 17` phải từ chối dù host JDK có thể hiểu cú pháp ấy.

**Không nhầm với `-source` và `-target` riêng lẻ:** `-source 17` kiểm soát cú pháp, `-target 17` kiểm soát mức class file, nhưng chỉ dùng hai tùy chọn đó trên một JDK mới không tự cung cấp hàng rào API nền tảng đúng mức như `--release 17`. Vì vậy khi xây artifact chạy trên một bản Java cụ thể, thường nên dùng `--release`.

Cũng cần nhớ:

- `--release N` chỉ có hiệu lực khi **bản `javac` đang chạy hỗ trợ N**; một JDK cũ không thể biên dịch cho một release tương lai mà nó không biết.
- `--release 17` **không mang theo** thư viện thứ ba tương thích Java 17. Dependency có thể yêu cầu bytecode cao hơn, dùng API không khả dụng hoặc có hợp đồng runtime khác.
- `--release 17` **không ép JVM runtime của ứng dụng phải là Java 17**, mà tạo artifact hướng tới mức ấy. JDK mới hơn thường chạy được bytecode 17, nhưng vẫn cần kiểm thử thư viện, module, cấu hình và hành vi ứng dụng.
- Tùy chọn `--release` không tự tải xuống/cài đặt JDK 17 cho máy.

### Khi nào `--release` khác “biên dịch bằng JDK 17”?

Biên dịch trên JDK 17 với cấu hình phù hợp và biên dịch trên JDK 21 với `--release 17` đều có thể tạo class file mức Java 17. Nhưng **host JDK, compiler implementation, lỗi/cảnh báo chi tiết, plugin, annotation processor và dependency của build** có thể khác nhau.

`--release` là cách rõ ràng để hướng tới API và class-file level của target release. Nó **không thay thế** việc kiểm thử artifact trên một JDK runtime thực sự nằm trong ma trận hỗ trợ.

## 3. `SourceVersion` dùng cho gì?

`SourceVersion` là enum ở:

```java
import javax.lang.model.SourceVersion;
```

Các hằng `SourceVersion.RELEASE_8`, `RELEASE_11`, `RELEASE_17`... biểu thị những phiên bản ngôn ngữ Java được API mô hình hóa trong JDK tương ứng. Khi phát hành một JDK mới, enum có thể có thêm hằng cho release mới.

Annotation processor thường khai báo:

```java
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;

@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ExampleProcessor
        extends javax.annotation.processing.AbstractProcessor {
    // ...
}
```

Đoạn trên **chỉ minh họa annotation cấu hình**, chưa đầy đủ phần thân processor và không phải ví dụ chạy độc lập.

Tác dụng:

- Thông báo **phiên bản nguồn mới nhất mà processor tự nhận hỗ trợ**.
- Compiler/processing tool có thể đối chiếu với version đang dùng và đưa ra **warning** nếu processor công bố mức thấp hơn phiên bản nguồn được yêu cầu.
- Cho người viết processor một cam kết kỹ thuật: processor nên có khả năng hiểu những `Element`, `ElementKind`, `TypeMirror` hoặc cấu trúc nguồn hợp lệ trong phạm vi nó công bố.

**Nó không:**

- đặt `javac` sang chế độ `--release 17`;
- sinh bytecode 17;
- kiểm tra rằng các dependency runtime đã tương thích Java 17;
- ngăn compiler phát sinh những warning hay error riêng;
- bảo đảm processor hoạt động đúng với mọi cú pháp mới chỉ nhờ đổi số hằng.

### Một đối chiếu rất quan trọng

| Cấu hình | Ai đọc? | Câu hỏi thực sự |
| --- | --- | --- |
| `javac --release 17` | Compiler | “Mã đang biên dịch phải phù hợp với bản Java nào về nguồn/API nền tảng/class file?” |
| `@SupportedSourceVersion(RELEASE_17)` | Hạ tầng annotation processing | “Processor tự công bố hỗ trợ mô hình nguồn đến bản nào?” |
| `javac -version` | Người cấu hình build/CI | “Compiler thật sự đang được chạy thuộc JDK nào?” |
| `java -version` | Người triển khai/CI | “Runtime `java` nào đang chạy tại môi trường này?” |
| `javap -verbose SomeClass` | Công cụ kiểm tra bytecode | “Artifact thực tế có class-file version nào?” |

Một processor có `RELEASE_17` có thể **chạy trên host JDK 21**. Nếu application được biên dịch bằng `--release 21`, processor ấy có thể bị cảnh báo là công bố source version thấp hơn mức yêu cầu; lời khai báo không tự chuyển mã ứng dụng xuống Java 17.

## 4. Host JDK quyết định khả năng *chạy* processor

Annotation processor là **mã Java thực sự được load và thực thi trong quá trình biên dịch**. Nó khác với mã ứng dụng đang được compiler phân tích.

Giả sử:

- Processor được biên dịch với **class file Java 21 (major 65)**.
- CI đang chạy `javac` bằng **JDK 17**, với JVM chỉ hiểu class file tới Java 17 (major 61).

Trong cấu hình đó, processor **không thể được JVM 17 tải bình thường**. Bạn có thể gặp lỗi như `UnsupportedClassVersionError` ngay cả khi ứng dụng đang được biên dịch với `--release 17`.

Ngược lại, nếu một processor được biên dịch thành bytecode Java 17 và không yêu cầu API/dependency cao hơn, một host JDK 21 thông thường có thể chạy nó khi biên dịch ứng dụng cho Java 17. Điều kiện quan trọng là **processor + dependency phải tương thích với host JVM thực tế**.

Do đó cần phân biệt hai artifact:

```text
processor.jar
   ├── bytecode của processor và dependencies
   └── chạy trong host JVM của javac

application.jar
   ├── bytecode ứng dụng do javac sinh ra
   └── chạy trên target runtime Java triển khai

Một lệnh build có thể cấu hình target release của hai
artifact này KHÁC NHAU.
```

**`--release` đặt trên lệnh biên dịch ứng dụng không tự biên dịch lại processor để chạy được trên host cũ.** Nếu processor đã tồn tại ở `processorpath`, JVM phải tải được bytecode của processor trước khi processor xử lý mã nguồn ứng dụng.

### Processor được biên dịch với bản Java nào?

Khi tự xuất bản processor thành thư viện, quyết định **minimum host JDK** mà tool cần hỗ trợ. Nếu muốn processor chạy trên JDK 17+, có thể biên dịch chính processor bằng `--release 17` trên compiler hỗ trợ release ấy, kiểm tra các dependency của nó, rồi kiểm thử trên JDK 17 thực.

Nếu ứng dụng target Java 8 nhưng đội build chạy processor trên JDK 17, bạn có thể biên dịch ứng dụng với `--release 8` và dùng một processor chạy được trên host 17. Tuy nhiên, phần **API được processor hiểu** và `@SupportedSourceVersion` vẫn phải phù hợp với mã được xử lý; không nên suy rằng processor phải có bytecode Java 8 chỉ vì output của ứng dụng là Java 8.

## 5. Quan hệ giữa Java modules, classpath và processor path

Khi dùng `javac`, có hai vai trò đường dẫn cần phân biệt:

- **Classpath/module path của ứng dụng:** compiler cần để tìm mã/thư viện tham chiếu bởi nguồn ứng dụng.
- **Processor path/processor module path:** hạ tầng annotation processing dùng để **tìm và tải mã processor**.

Trong ví dụ Java 17+ ở dưới, processor được biên dịch riêng ra thư mục `processor-classes` rồi được cung cấp cho bước biên dịch ứng dụng bằng:

```bash
-processorpath processor-classes -processor lesson.CheckApiProcessor
```

`-processorpath` chỉ đường dẫn chứa processor; `-processor` chọn rõ class processor cần chạy. Để compiler cũng thấy **loại annotation `CheckApi`** mà nguồn ứng dụng sử dụng, ví dụ còn đặt `processor-classes` trong **`-cp`** khi biên dịch ứng dụng.

Đây là sự tách biệt **mã chạy lúc build** và **mã được ứng dụng tham chiếu**. Một hệ thống build khác có thể đóng gói annotation API và processor vào hai JAR riêng; khi đó annotation API nằm trên compile classpath, processor implementation nằm trên processor path.

### Đừng chỉ dựa vào tự khám phá processor

Một processor có thể được đăng ký bằng service file thích hợp, hoặc được chỉ định tường minh qua `-processor`. Phần hướng dẫn dùng `-processor` để **không phụ thuộc cơ chế auto-discovery** và tránh bất đồng giữa phiên bản JDK/build tool.

Từ một số bản JDK mới, cấu hình mặc định cho việc tự kích hoạt processor có thể thay đổi. Dù dùng Maven, Gradle hay gọi `javac` trực tiếp, hãy **khai báo tường minh processor và dependency cần thiết** để build ổn định, thay vì trông chờ mọi compiler luôn tự chạy processor có mặt trên classpath.

## 6. Ví dụ Java 17+ hoàn chỉnh: processor và ứng dụng biên dịch hai giai đoạn

Ta dùng **JDK 17 hoặc mới hơn có hỗ trợ `--release 17`**. Ví dụ có một processor chạy lúc build và một ứng dụng chạy lúc runtime. Processor được công bố hỗ trợ `SourceVersion.RELEASE_17`, còn hai lệnh biên dịch dùng `--release 17` rõ ràng.

Cấu trúc:

```text
project/
└── src/
    └── lesson/
        ├── CheckApiProcessor.java
        └── Demo.java
```

### File 1: `src/lesson/CheckApiProcessor.java`

```java
package lesson;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface CheckApi {}

@SupportedAnnotationTypes("lesson.CheckApi")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CheckApiProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(CheckApi.class)) {

            if (element.getKind() == ElementKind.CLASS) {
                TypeElement type = (TypeElement) element;
                System.out.println("PROCESSOR: "
                        + type.getQualifiedName());
            }
        }

        return true;
    }
}
```

**Vai trò từng thành phần:**

- `CheckApi` là annotation nội bộ của ví dụ, chỉ dùng compile-time vì retention `SOURCE`.
- `@SupportedAnnotationTypes("lesson.CheckApi")` đăng ký loại annotation mà processor xử lý.
- `@SupportedSourceVersion(RELEASE_17)` khai báo phạm vi phiên bản nguồn processor hỗ trợ; nó **không thay thế** `--release`.
- `roundEnv.getElementsAnnotatedWith(CheckApi.class)` nhận các thành phần trực tiếp mang annotation.
- `ElementKind.CLASS` chọn class, còn `TypeElement.getQualifiedName()` in tên đủ điều kiện.
- `roundEnv.processingOver()` tránh in thêm trong vòng xử lý kết thúc.
- `return true` cho biết processor đã xử lý/claim annotation được hỗ trợ trong round tương ứng.

### File 2: `src/lesson/Demo.java`

```java
package lesson;

@CheckApi
public class Demo {
    public static void main(String[] args) {
        System.out.println("APPLICATION: running");
    }
}
```

### Lệnh biên dịch và chạy

Trong thư mục `project`, tạo hai thư mục output rồi chạy các lệnh. Các lệnh dưới đây dùng **Bash** trên Linux/macOS hoặc shell tương thích:

```bash
mkdir -p processor-classes app-classes
javac --release 17 -encoding UTF-8 -d processor-classes src/lesson/CheckApiProcessor.java
javac --release 17 -encoding UTF-8 -cp processor-classes -processorpath processor-classes -processor lesson.CheckApiProcessor -d app-classes src/lesson/Demo.java
java -cp app-classes lesson.Demo
```

Nếu dùng PowerShell trên Windows, có thể thay dòng `mkdir -p` bằng:

```powershell
New-Item -ItemType Directory -Force processor-classes, app-classes
```

Các lệnh `javac`/`java` còn lại về bản chất giống nhau.

**Stdout của bước biên dịch ứng dụng thứ hai:**

```text
PROCESSOR: lesson.Demo
```

**Stdout của bước chạy chương trình cuối:**

```text
APPLICATION: running
```

Bước biên dịch processor đầu tiên không in thêm thông điệp nếu thành công. Bước biên dịch ứng dụng được gọi `-processor lesson.CheckApiProcessor` nên processor được kích hoạt tường minh và phát dòng `PROCESSOR: ...`. Chương trình cuối chạy `Demo.main` và in `APPLICATION: running`.

**Điểm học tập:** annotation processor **đã chạy khi biên dịch**, không phải lúc `Demo.main` thực thi. Tệp `Demo.class` biên dịch với mức Java 17, trong khi `@CheckApi` có retention `SOURCE` nên cách sử dụng marker đó không được giữ lại làm annotation runtime.

## 7. Kiểm tra kết quả: compiler, runtime và bytecode

Đầu tiên xác minh phiên bản công cụ thực tế:

```bash
javac -version
java -version
```

Đây là các lệnh kiểm tra môi trường; **không có một stdout cố định** áp dụng cho mọi máy. Chẳng hạn phiên bản có thể là 17 hoặc 21, và việc `java` và `javac` cùng nằm trên `PATH` có thể cần kiểm tra nếu máy cài nhiều JDK.

Sau khi biên dịch ví dụ thành công, xem mức class file:

```bash
javap -verbose -classpath app-classes lesson.Demo
javap -verbose -classpath processor-classes lesson.CheckApiProcessor
```

Trong phần thông tin class file, class ứng dụng được biên dịch bằng `--release 17` sẽ có **major version: 61**. Ở đây ta **cũng chủ động** dùng `--release 17` khi biên dịch processor, nên `CheckApiProcessor.class` cũng có major version 61.

Tuy nhiên, đây là kết quả của **hai lệnh biên dịch độc lập**. Nếu thay bước biên dịch processor bằng một lệnh khác nhắm Java 21, class file của processor có thể có major version 65 mà không làm thay đổi việc ứng dụng `Demo` vẫn được biên dịch với `--release 17`.

### Bảng kiểm tra nhanh

| Quan sát | Ý nghĩa |
| --- | --- |
| `javac -version` hiển thị 21 | Đang chạy compiler của JDK 21 |
| Lệnh ứng dụng có `--release 17` | Yêu cầu output tương thích nguồn/API/bytecode Java 17 |
| `@SupportedSourceVersion(RELEASE_17)` | Processor tự công bố hỗ trợ source level Java 17 |
| `javap` của `Demo.class` hiển thị major `61` | Class file ứng dụng nhắm Java 17 |
| `javap` của processor hiển thị major `61` | Processor được build cho JVM hỗ trợ class file 61 |
| `java -cp app-classes lesson.Demo` chạy được trên Java 17 | Một phép kiểm thực tế trong môi trường đó, không phải bảo đảm mọi môi trường khác giống hệt |

Khi nghi ngờ sự không khớp, hãy kiểm tra **phiên bản thực của mọi công cụ**, chứ không chỉ đọc một cấu hình `sourceCompatibility` trong build script.

## 8. Các cấu hình hợp lý và các lỗi thường gặp

| Host JDK | Compile ứng dụng | Processor | Đánh giá |
| --- | --- | --- | --- |
| 17 | `--release 17` | Build bytecode 17; công bố `RELEASE_17` | Phù hợp nếu dependency cũng tương thích |
| 21 | `--release 17` | Build bytecode 17; công bố `RELEASE_17` | Phù hợp, processor chạy trên host 21; ứng dụng hướng Java 17 |
| 17 | `--release 21` | Bất kỳ | Không khả thi với `javac` JDK 17 vì không biết target release 21 |
| 17 | `--release 17` | Processor build cho bytecode 21 | Không tải được processor trên JVM 17; có thể gặp `UnsupportedClassVersionError` |
| 21 | `--release 21` | Processor chỉ công bố `RELEASE_17` | Compiler có thể cảnh báo supported source version thấp hơn requested source 21; không tự downgrade ứng dụng |
| 21 | `--release 17` | Processor dùng API chỉ có ở Java 21 và compile cho 21 | Có thể chạy trên host 21, nhưng không phải processor tương thích host JDK 17 |

Bảng là **ma trận khái niệm**: kết quả cuối cùng còn tùy dependency, module, plugin và chính xác bản JDK/compiler được dùng.

### Tại sao compiler warning về supported source version?

Khi một processor hỗ trợ nguồn đến `RELEASE_17` nhưng lệnh biên dịch ứng dụng yêu cầu source level mới hơn, `javac` có thể phát cảnh báo dạng “Supported source version ... less than -source ...”.

Đây là tín hiệu rằng **processor chưa tự công bố hiểu những mô hình/cú pháp mới**. Nó không nhất thiết có nghĩa annotation processor sẽ bị từ chối hoàn toàn; nhưng đội dự án cần kiểm tra processor với syntax/element mới trước khi cập nhật `SourceVersion`.

Không nên xử lý warning bằng cách “nâng số hằng `RELEASE_17` lên `RELEASE_21`” trong source rồi bỏ qua mọi test. Processor có thể có logic `switch` trên `ElementKind`, giới hạn loại kiểu hoặc thuật toán AST phụ thuộc cú pháp cũ. Cập nhật phạm vi hỗ trợ phải dựa trên **kiểm thử thực tế**.

### Khi nào dùng `SourceVersion.latestSupported()`?

Một số processor override:

```java
@Override
public javax.lang.model.SourceVersion getSupportedSourceVersion() {
    return javax.lang.model.SourceVersion.latestSupported();
}
```

Đây là **trích đoạn minh họa**, không phải lớp processor đầy đủ. Phương thức trả về phiên bản nguồn mới nhất được môi trường thực thi hỗ trợ theo API. Nó thuận tiện cho processor thực sự theo kịp sự phát triển JDK, nhưng **không chứng minh** logic processor đã tương thích với mọi cấu trúc mới.

So với `@SupportedSourceVersion(RELEASE_17)`, cách này báo mức hỗ trợ phụ thuộc môi trường đang chạy. Nếu chỉ kiểm thử/đảm bảo Java 17, công bố `RELEASE_17` có thể trung thực và dễ duy trì hơn; nếu processor có chiến lược hỗ trợ phiên bản mới, có thể dùng `latestSupported()` sau khi thiết kế kiểm thử phù hợp.

`SourceVersion.latest()` và `latestSupported()` không nhất thiết có cùng vai trò: phiên bản mới nhất được enum khai báo và phiên bản mới nhất được môi trường hiện tại hỗ trợ có thể khác trong một số trường hợp. Không lấy một trong hai làm thay thế cho cài đặt `--release`.

## 9. Quan hệ với Maven, Gradle và JDK toolchains

Trong dự án thật, `javac` có thể được gọi gián tiếp qua Maven, Gradle, IDE hoặc CI. Dù công cụ build sử dụng cú pháp cấu hình riêng, vẫn nên xác định rõ:

1. **JDK dùng để chạy build/compiler.**
2. **Mức `release` của mã ứng dụng.**
3. **Nguồn/target và bytecode của processor artifact**, nếu bạn phát triển processor.
4. **Processor path** và các dependency của processor.
5. **Mức source mà processor công bố**, chẳng hạn `RELEASE_17`.
6. **JDK runtime triển khai** và phiên bản thực của các thư viện.

Ví dụ, dùng Java toolchain có thể giúp chọn JDK compiler cụ thể. Nhưng **toolchain** và **release target** giải quyết hai câu hỏi khác nhau: chọn compiler/JDK để chạy build, và chọn mức API/bytecode cho mã được sinh ra. Đừng coi `JAVA_HOME`, `--release` và `@SupportedSourceVersion` là ba cách viết của cùng một cấu hình.

Nếu dự án có **module riêng cho processor**, hãy build và kiểm thử module đó như một công cụ chạy lúc build. Nếu ứng dụng target Java 11 nhưng hệ thống build cố định host JDK 21, processor có thể chạy trên JDK 21 và khai báo source support phù hợp với Java 11 trong khi mã ứng dụng được biên dịch với `--release 11`.

### Đầu ra build không chỉ là bytecode

Một annotation processor có thể tạo thêm source/resource qua `Filer`. Khi sinh source cho ứng dụng target Java 17, **nội dung source được sinh** cũng phải dùng cú pháp/API phù hợp Java 17; nếu không, những vòng biên dịch kế tiếp có thể lỗi dù `@SupportedSourceVersion` ghi một hằng bất kỳ.

Tương tự, nếu một processor ghi ra class file hoặc gọi công cụ phụ độc lập, cần kiểm tra mục tiêu phiên bản của artifact sinh ra. Không thể suy rằng mọi file được một công cụ tùy chỉnh sinh ra đều tự được `--release` điều chỉnh nếu chúng không đi qua bước biên dịch tương ứng.

## 10. Những hiểu nhầm thường gặp

**Lỗi 1 — “`@SupportedSourceVersion(RELEASE_17)` làm class file chạy được trên Java 17.”** Sai. Thuộc tính đó nói về nguồn processor hỗ trợ; mức class file do compiler target quyết định.

**Lỗi 2 — “Dùng JDK 21 thì chắc chắn code không chạy trên Java 17.”** Sai. JDK 21 có thể biên dịch ứng dụng với `--release 17`, nếu mã và dependency tương thích.

**Lỗi 3 — “`-source 17 -target 17` luôn tương đương `--release 17`.”** Sai trong kiểm soát API nền tảng khi dùng compiler mới; `--release` còn giới hạn API của release đích.

**Lỗi 4 — “Processor chạy trong JVM Java 17 dù `javac` đang chạy bằng JDK 21.”** Không mặc nhiên. Processor thường thực thi trong môi trường compiler/host, không phải JVM của runtime đích.

**Lỗi 5 — “Application target 8 thì processor cũng phải build cho Java 8.”** Không nhất thiết. Processor chạy trên host JDK dùng lúc biên dịch; target của application độc lập với bytecode của processor, nhưng phải kiểm tra khả năng tương thích host.

**Lỗi 6 — “Nâng `SourceVersion` là đủ để hiểu record, sealed hoặc syntax mới.”** Không. Cần đánh giá mô hình mới, logic validation/generation và kiểm thử.

**Lỗi 7 — “`--release 17` tự động sửa các dependency biên dịch bằng Java 21.”** Không. Thư viện bên ngoài có yêu cầu riêng; phải chọn bản dependency tương thích và kiểm thử runtime.

**Lỗi 8 — “Annotation retention `RUNTIME` mới kích hoạt được processor.”** Không. Annotation processor hoạt động lúc build; retention `SOURCE` có thể đủ, miễn processor được cấu hình chạy.

**Lỗi 9 — “Có JAR processor trên classpath thì ở mọi JDK nó luôn tự chạy.”** Không an toàn. Cơ chế tự khám phá mặc định khác nhau theo cấu hình và phiên bản; nên khai báo processor path/processor rõ ràng.

**Lỗi 10 — “Build thành công là chứng minh runtime Java 17 chạy được mọi thứ.”** Không. Build kiểm chứng nguồn/bytecode trong phạm vi compiler, còn runtime còn phụ thuộc JDK thực, library và môi trường triển khai.

## 11. Bài tập tự kiểm tra

**Bài 1.** Một dự án dùng `javac` JDK 21, đặt `--release 17` và processor công bố `RELEASE_17`. Phần nào quyết định class file của ứng dụng có major version 61?

**Đáp án:** `--release 17` ở **lệnh biên dịch ứng dụng**, không phải `SourceVersion.RELEASE_17` trên processor.

**Bài 2.** Cũng dự án trên, JVM nào chạy mã processor?

**Đáp án:** Môi trường JVM của quá trình compiler/host JDK tương ứng, không tự chuyển sang Java 17 chỉ vì `--release 17`.

**Bài 3.** Vì sao processor biên dịch bằng Java 21 có thể không chạy khi dùng `javac` JDK 17?

**Đáp án:** Bytecode processor có thể là major 65, vượt mức JVM 17 hỗ trợ; JVM báo lỗi class version như `UnsupportedClassVersionError`.

**Bài 4.** Processor có `@SupportedSourceVersion(RELEASE_17)`, nhưng ứng dụng build với `--release 21` trên JDK 21. Điều gì đáng chú ý?

**Đáp án:** Compiler có thể cảnh báo processor chỉ công bố hỗ trợ đến release 17; cần xác minh processor hiểu các đặc tính nguồn mới, không tự downgrade application.

**Bài 5.** `Package.getName()` hay `SourceVersion` có giúp giới hạn API nền tảng Java 17 khi dùng JDK 21 không?

**Đáp án:** Không. Công việc kiểm soát API nền tảng theo bản target thuộc `javac --release 17`.

**Bài 6.** Vì sao ví dụ phải biên dịch `CheckApiProcessor.java` trước `Demo.java`?

**Đáp án:** Processor phải trở thành class có thể được compiler tải và sử dụng trong bước annotation processing tiếp theo; file nguồn ứng dụng cũng cần nhìn thấy định nghĩa `CheckApi`.

**Bài 7.** Nếu chạy `javap -verbose` trên `Demo.class` và thấy major version 61, điều đó chứng minh điều gì?

**Đáp án:** Class file được sinh với mức bytecode Java 17. Nó không một mình chứng minh mọi dependency/module và hành vi runtime đều tương thích.

**Bài 8.** Đổi `@Retention(SOURCE)` thành `RUNTIME` trên `CheckApi` có phải điều kiện để `CheckApiProcessor` phát hiện `Demo` lúc biên dịch không?

**Đáp án:** Không. Processor quan sát annotation ở compile-time; retention `SOURCE` đã đủ trong ví dụ.

**Bài 9.** Tại sao có thể dùng `SourceVersion.latestSupported()` mà vẫn phải kiểm thử processor trên JDK mới?

**Đáp án:** API trả một mức phiên bản được môi trường hỗ trợ, nhưng không bảo đảm logic phân tích/generate của processor đã hiểu mọi cấu trúc ngôn ngữ mới.

**Bài 10.** Một build tool cung cấp JDK toolchain 21 và target `release = 17`. Hai cấu hình ấy có trùng nghĩa không?

**Đáp án:** Không. Toolchain chọn **JDK/compiler dùng để build**; release chọn **mức nguồn/API nền tảng/class file** của ứng dụng.

## 12. Tổng kết

Muốn xây một annotation processor và ứng dụng Java có thể bảo trì lâu dài, hãy viết rõ **ba hợp đồng tương thích**: **host JDK chạy compiler/processor**, **`--release` cho mã ứng dụng hoặc artifact cần phát hành**, và **`SourceVersion` mà processor công bố hỗ trợ**. Kiểm tra thêm phiên bản bytecode/dependency, môi trường Java runtime triển khai và nguồn Java do processor sinh.

Không dùng `@SupportedSourceVersion` thay cho `--release`, cũng không dùng `--release` để suy rằng processor được xây dựng cho đúng JVM runtime của ứng dụng. Khi tách ba nhiệm vụ này, việc tìm lỗi build và nâng cấp JDK sẽ rõ ràng, có thể kiểm thử và ít bất ngờ hơn.
