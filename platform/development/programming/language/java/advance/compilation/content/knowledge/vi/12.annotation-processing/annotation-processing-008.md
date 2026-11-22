# Thư mục nguồn sinh `-s` và quan hệ với thư mục class trong Java

Trong pipeline biên dịch Java có **annotation processing**, một processor có thể sinh thêm tệp mã nguồn `.java`. Trình biên dịch `javac` có hai nơi nhận output khác nhau: **`-s <dir>` để lưu nguồn Java được sinh**, và **`-d <dir>` để lưu các tệp `.class` đã được biên dịch**. Hai thư mục có thể liên quan cùng một kiểu Java, nhưng chứa **hai loại artifact ở hai giai đoạn khác nhau**, không thay thế nhau.

Đây là bài về *xử lý annotation*, không phải chỉ là lệnh tạo thư mục. Cần hiểu processor sinh mã lúc nào, `javac` đưa mã đó qua các processing rounds ra sao, vì sao đôi khi thấy `Generated.java` nhưng chưa có `Generated.class`, và cách cấu hình build để tránh trộn source/generated code với class output.

## 1. Bản đồ tổng thể của annotation processing

~~~text
Source gốc (*.java) + annotations
                |
                v
             javac
       phân tích nguồn, kiểu
                |
                v
       Annotation processor(s)
                |     javax.annotation.processing.Processor
                |     Filer.createSourceFile(...)
                v
   Nguồn Java sinh thêm (*.java)
                |
                +-------> -s build/generated-sources/
                |
                v
   Processing round tiếp theo (khi có source mới)
                |
                v
      Compiler phân tích + sinh bytecode
                |
                +-------> -d build/classes/
                            *.class, kể cả class từ source sinh ra
~~~

Quy trình khái niệm:

1. `javac` đọc nguồn ban đầu và xác định annotations/processor phù hợp.
2. Một processor được chạy trong *processing rounds*. Processor có thể dùng `javax.annotation.processing.Filer` để tạo nguồn mới.
3. Source file được tạo trong **`SOURCE_OUTPUT`**, chính là vị trí do `-s` chỉ định khi option này có mặt.
4. Các source files mới được đưa vào những round tiếp theo và, trong chế độ compilation bình thường, có thể được `javac` biên dịch thành bytecode.
5. Class files được ghi trong **`CLASS_OUTPUT`**, tức thư mục do `-d` chỉ định.

Điểm mấu chốt: **`-s` không có nghĩa yêu cầu compiler sinh nguồn bằng mọi giá.** Nó chỉ đặt *đích* cho source file mà annotation processor có khả năng tạo. Nếu không có processor phù hợp, không có annotation được xử lý hoặc processor không sinh nguồn, `-s` có thể không có tệp mới.

Tương tự, `-d` không tự động kích hoạt annotation processing; nó xác định nơi đặt kết quả class files của compiler.

## 2. Ý nghĩa chính xác của `-s` và `-d`

| Tiêu chí | `javac -s DIR` | `javac -d DIR` |
| --- | --- | --- |
| Mục đích | Đích **generated source files** | Đích **compiled class files** |
| Kiểu file thường gặp | `.java` do annotation processor sinh | `.class` từ nguồn gốc và nguồn sinh |
| API tương ứng trong processor | `StandardLocation.SOURCE_OUTPUT` | `StandardLocation.CLASS_OUTPUT` |
| Ai tạo nội dung? | Processor dùng `Filer.createSourceFile` | `javac` sinh bytecode, hoặc processor dùng `Filer.createClassFile` trong tình huống chuyên biệt |
| Có cần source sinh ra? | Không: thư mục có thể rỗng | Không: mã nguồn thường vẫn sinh `.class` khi compile thành công |
| Cách đặt đường dẫn theo package | `demo.GeneratedGreeting` → `DIR/demo/GeneratedGreeting.java` | `demo.GeneratedGreeting` → `DIR/demo/GeneratedGreeting.class` |
| Đầu vào cho `java -cp` | Không dùng thư mục source như classpath runtime | Dùng thư mục chứa class files |
| Cách dùng phổ biến | Inspect/debug generated code; hỗ trợ IDE; kiểm tra đầu ra processor | Chạy/test/đóng gói ứng dụng |

Hai thư mục **nên khác nhau** và khác cả source gốc:

~~~text
project/
├── processor-src/             # Mã nguồn của annotation và processor
├── app-src/                   # Mã nguồn viết tay
├── build/
│   ├── processor-classes/     # Processor và annotation đã được biên dịch
│   ├── generated-sources/     # Đích của -s
│   └── classes/               # Đích của -d
~~~

Ví dụ `build/generated-sources/demo/GeneratedGreeting.java` và `build/classes/demo/GeneratedGreeting.class` tương ứng **cùng một kiểu `demo.GeneratedGreeting`**, nhưng tệp thứ nhất là nguồn có thể đọc, tệp thứ hai là artifact nhị phân JVM thực thi.

**Đừng nhầm `-s` của `javac` với `-source` hoặc `--source`**: `-s` chỉ thư mục nguồn do processor sinh; `--source 17` chỉ mức cú pháp Java. Tương tự, `--release 17` là lựa chọn tương thích language/API/bytecode, không đặt output directory.

## 3. Ví dụ đầy đủ: processor sinh `GeneratedGreeting.java`

Ví dụ chạy với **JDK 17+**, chỉ dùng API tiêu chuẩn, không cần Maven/Gradle hay thư viện bên thứ ba. Ta tạo một annotation `@AutoInfo`, một annotation processor và một chương trình ứng dụng dùng class mới được sinh.

### 3.1. Cây tệp trước khi biên dịch

~~~text
sample/
├── processor-src/
│   └── demo/
│       ├── AutoInfo.java
│       └── GreetingProcessor.java
└── app-src/
    └── demo/
        ├── Request.java
        └── App.java
~~~

Đặt đúng các file dưới đây, rồi chạy các lệnh từ thư mục `sample/`.

### 3.2. Định nghĩa annotation

**`processor-src/demo/AutoInfo.java`**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface AutoInfo {
}
~~~

`RetentionPolicy.SOURCE` là đủ cho annotation processor đọc annotation trong quá trình compile; không cần giữ annotation trong class file/runtime cho chức năng sinh mã của ví dụ.

### 3.3. Viết annotation processor

**`processor-src/demo/GreetingProcessor.java`**

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.AutoInfo")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (generated || roundEnv.processingOver() ||
            roundEnv.getElementsAnnotatedWith(AutoInfo.class).isEmpty()) {
            return true;
        }

        generated = true;
        try {
            var file = processingEnv.getFiler()
                    .createSourceFile("demo.GeneratedGreeting");
            try (Writer writer = file.openWriter()) {
                writer.write("package demo;\n"
                    + "public final class GeneratedGreeting {\n"
                    + "  private GeneratedGreeting() {}\n"
                    + "  public static String message() { return \"generated-ok\"; }\n"
                    + "}\n");
            }
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot generate source", ex);
        }
        return true;
    }
}
~~~

Giải thích các điểm quan trọng:

- `AbstractProcessor` thực hiện interface processor chuẩn.
- `@SupportedAnnotationTypes("demo.AutoInfo")` khai báo annotation name mà processor hỗ trợ. Tên đó **không phải** tên tệp nguồn sinh.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)` khai báo khả năng xử lý source Java 17; điều này khác `javac --release 17` dùng để đặt compilation target.
- `roundEnv.getElementsAnnotatedWith(AutoInfo.class)` tìm declarations có annotation. Nếu không có, processor không sinh tệp.
- `processingEnv.getFiler().createSourceFile("demo.GeneratedGreeting")` tạo một `JavaFileObject` thuộc location `SOURCE_OUTPUT`; tên được cung cấp là **tên kiểu đã đủ package**, không phải đường dẫn filesystem.
- `openWriter()` ghi toàn bộ Java source mới, bao gồm `package demo;`.
- Biến `generated` ngăn thử tạo cùng một source file lần nữa ở round tiếp theo; `roundEnv.processingOver()` tránh sinh file ở round kết thúc. Trong dự án thật, cũng cần thiết kế việc ghi nhiều file/nguồn và xử lý lỗi cẩn thận.

**Không viết trực tiếp `new File("build/generated-sources/...")` trong processor để né `Filer`**: `Filer` cung cấp một cơ chế được compiler quản lý để đặt output theo package, ghi nhận source mới cho processing rounds và phát hiện nhiều tình huống tạo trùng.

### 3.4. Source ứng dụng kích hoạt processor

**`app-src/demo/Request.java`**

~~~java
package demo;

@AutoInfo
public final class Request {
}
~~~

**`app-src/demo/App.java`**

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.message());
    }
}
~~~

Lúc mới tạo dự án, **không có** file `GeneratedGreeting.java` hay `GeneratedGreeting.class`. App tham chiếu một kiểu sẽ được processor sinh trong compilation. Vì vậy cần cấu hình processor chính xác.

### 3.5. Lần biên dịch thứ nhất: tạo processor đã compile

Tạo ba thư mục output bằng Bash/Linux/macOS:

~~~bash
mkdir -p build/processor-classes build/generated-sources build/classes
~~~

PowerShell có thể tạo tương ứng bằng:

~~~powershell
New-Item -ItemType Directory -Force -Path build/processor-classes,build/generated-sources,build/classes
~~~

Biên dịch annotation và processor (chưa compile app):

~~~bash
javac --release 17 -d build/processor-classes processor-src/demo/AutoInfo.java processor-src/demo/GreetingProcessor.java
~~~

Sau lệnh này:

~~~text
build/processor-classes/
└── demo/
    ├── AutoInfo.class
    └── GreetingProcessor.class
~~~

**Chưa có `GeneratedGreeting.java`** vì ở lần compile này ta chỉ xây dựng processor, chưa chạy processor trên `@AutoInfo` của `Request`. Đây là phân tách phổ biến giữa module thư viện processor và module ứng dụng tiêu thụ processor.

### 3.6. Lần biên dịch thứ hai: chạy processor, ghi `-s` và `-d`

~~~bash
javac --release 17 -cp build/processor-classes -processorpath build/processor-classes -processor demo.GreetingProcessor -s build/generated-sources -d build/classes app-src/demo/Request.java app-src/demo/App.java
~~~

Ý nghĩa từng option:

1. `--release 17`: mục tiêu cú pháp/API/bytecode Java 17.
2. `-cp build/processor-classes`: cho compiler nhìn thấy declaration của annotation `demo.AutoInfo` được `Request.java` dùng.
3. `-processorpath build/processor-classes`: cho cơ chế annotation processing tìm/đọc processor và dependency cần thiết của nó.
4. `-processor demo.GreetingProcessor`: **chỉ rõ processor cần thực thi**, thay vì dựa vào auto-discovery. Cách này cũng tránh khác biệt về mặc định chạy processors giữa các đời JDK.
5. `-s build/generated-sources`: hướng nguồn Java mới do processor tạo tới thư mục này.
6. `-d build/classes`: hướng class files của nguồn gốc **và nguồn sinh** tới thư mục này.
7. `app-src/demo/Request.java app-src/demo/App.java`: input files thuộc compilation hiện tại.

**Khi compile thành công, `javac` thông thường không in stdout.** Trong ví dụ, thư mục nguồn sinh:

~~~text
build/generated-sources/
└── demo/
    └── GeneratedGreeting.java
~~~

File `GeneratedGreeting.java` chứa:

~~~java
package demo;
public final class GeneratedGreeting {
  private GeneratedGreeting() {}
  public static String message() { return "generated-ok"; }
}
~~~

Thư mục class files:

~~~text
build/classes/
└── demo/
    ├── App.class
    ├── Request.class
    └── GeneratedGreeting.class
~~~

Điều dễ bỏ sót: **không cần gọi `javac` lần thứ ba để biên dịch `GeneratedGreeting.java`** trong cách build bình thường này. `javac` nhận source được sinh qua `Filer`, đưa nó vào processing/compilation theo cơ chế annotation processing và cuối cùng sinh `GeneratedGreeting.class`.

### 3.7. Chạy ứng dụng sau khi compile

~~~bash
java -cp build/classes demo.App
~~~

**Stdout chính xác:**

~~~text
generated-ok
~~~

Class `GeneratedGreeting.class` nằm trên runtime classpath nên JVM có thể nạp và chạy. Vì ví dụ dùng annotation với `SOURCE` retention và ứng dụng không tham chiếu `AutoInfo` lúc chạy, runtime classpath chỉ cần `build/classes` cho chương trình đơn giản này.

**Không chạy**:

~~~bash
java -cp build/generated-sources demo.App
~~~

vì `build/generated-sources` chứa Java source chứ không phải các class files của ứng dụng. Đây không phải runtime classpath đúng cho ví dụ.

## 4. Vì sao có nhiều processing rounds?

Annotation processing không nhất thiết chỉ có một bước. Mỗi round thấy một tập các Java elements đã được compiler cung cấp. Khi processor sinh thêm source hoặc class files, compiler có thể thực hiện round tiếp theo để các processor khác quan sát những elements mới.

Với ví dụ:

~~~text
Round đầu:
  Request.java có @AutoInfo
  GreetingProcessor tạo GeneratedGreeting.java

Round tiếp theo:
  Compiler nhận diện source mới
  Processor có thể thấy elements phát sinh từ source đó
  GreetingProcessor không tạo lại file (generated = true)

Round kết thúc:
  roundEnv.processingOver() = true
  Không tạo thêm source mới

Giai đoạn compilation bình thường:
  Sinh App.class, Request.class, GeneratedGreeting.class
~~~

Đây là mô hình để giải thích hành vi; thứ tự chi tiết giữa các compiler passes không phải hợp đồng công khai buộc mọi `javac` implementation có log giống hệt. Có thể bật các option chẩn đoán của `javac` để quan sát processing rounds (xem phần 8).

Các quy tắc đáng lưu ý:

- Processor **không nên tạo cùng một file type/resource nhiều lần trong cùng compilation**. `Filer` có thể ném `FilerException` khi path/tên đã được tạo hoặc đã tồn tại như input tương ứng.
- Source được sinh ở round trước có thể ảnh hưởng việc resolve types ở round sau.
- Một processor có thể **không sinh Java source** mà chỉ kiểm tra annotations, báo lỗi qua `Messager`, sinh tài nguyên cấu hình hoặc sinh binary class file theo hợp đồng `Filer`.
- Nếu processor phát sinh source sai cú pháp hoặc lỗi kiểu, compilation cuối cùng vẫn có thể thất bại, dù file `.java` đã xuất hiện trong `-s`.

## 5. Khi chỉ muốn sinh nguồn: `-proc:only`

Đôi khi muốn kiểm tra nguồn mà processor sẽ tạo, nhưng **chưa muốn biên dịch ứng dụng thành class files**. Dùng:

~~~bash
mkdir -p build/only-sources build/only-classes
javac --release 17 -cp build/processor-classes -processorpath build/processor-classes -processor demo.GreetingProcessor -proc:only -s build/only-sources -d build/only-classes app-src/demo/Request.java app-src/demo/App.java
~~~

Với PowerShell, tạo hai thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force -Path build/only-sources,build/only-classes
~~~

Kết quả trong ví dụ:

~~~text
build/only-sources/
└── demo/
    └── GeneratedGreeting.java

build/only-classes/
    (không có App.class, Request.class, GeneratedGreeting.class)
~~~

`-proc:only` yêu cầu thực hiện **annotation processing mà không compile các class Java thông thường**. Nó rất hữu ích để inspect codegen và chia nhỏ pipeline. `-d` không bị thay đổi ý nghĩa: compiler chỉ không đi đến bước tạo class files của ứng dụng do mode được chọn.

Sau khi đã có generated source, nếu muốn compile **riêng bước tiếp theo**, có thể làm như sau:

~~~bash
mkdir -p build/manual-classes
javac --release 17 -proc:none -cp build/processor-classes -d build/manual-classes app-src/demo/Request.java app-src/demo/App.java build/only-sources/demo/GeneratedGreeting.java
java -cp build/manual-classes demo.App
~~~

Stdout vẫn:

~~~text
generated-ok
~~~

Ở đây `-proc:none` **tắt annotation processing**, còn generated source được chỉ định rõ như một input file của lần `javac` thứ hai. Đây là pipeline hai bước **do người build chủ động điều phối**, khác với biên dịch bình thường một lượt ở phần 3.6. Nếu không đưa generated source vào compilation thứ hai (và cũng không có class tương ứng trên classpath), `App.java` sẽ không resolve được `GeneratedGreeting`.

**Không lầm tưởng `-proc:only` tạo đủ runtime artifact:** chạy `java -cp build/only-sources ...` sẽ không chạy được ví dụ vì không có compiled classes.

## 6. Khi tắt processing: `-proc:none`

Với cùng nguồn `Request.java` và `App.java`, nếu compile như sau trên output rỗng:

~~~bash
javac --release 17 -proc:none -cp build/processor-classes -d build/classes app-src/demo/Request.java app-src/demo/App.java
~~~

Compiler không chạy `GreetingProcessor`, nên không có `GeneratedGreeting` mới. Vì `App.java` tham chiếu kiểu chưa tồn tại trên classpath, lệnh **thất bại** với chẩn đoán kiểu `cannot find symbol: GeneratedGreeting`.

Đây là **ví dụ cố ý sai** nhằm phân biệt:

- `-proc:none` = không chạy annotation processor.
- `-proc:only` = chạy processing, không đi đến compilation class thông thường.
- Lệnh compile bình thường với `-processor ...` = processing + compilation, có thể tạo cả `.java` và `.class`.

Nếu một lần build trước để lại `GeneratedGreeting.class` trong nơi compiler đang tìm kiếm, việc tắt processor có thể bị che bởi stale bytecode; khi kiểm chứng hãy dùng **thư mục output mới/sạch** và đường tìm kiếm đầu vào rõ ràng.

## 7. Nếu không chỉ định `-s`?

Theo cách hoạt động của `javac`, khi processor sinh `.java` mà **không có `-s`**, generated source files sẽ được đặt **cùng vùng class output** (nơi `-d` chỉ định) thay vì một thư mục generated-sources riêng.

Ví dụ:

~~~bash
javac --release 17 -cp build/processor-classes -processorpath build/processor-classes -processor demo.GreetingProcessor -d build/mixed-output app-src/demo/Request.java app-src/demo/App.java
~~~

Giả sử `build/mixed-output` đã được tạo, có thể xuất hiện:

~~~text
build/mixed-output/
└── demo/
    ├── App.class
    ├── Request.class
    ├── GeneratedGreeting.java
    └── GeneratedGreeting.class
~~~

Điều này **không sai cú pháp**, nhưng làm nguồn sinh và binary output bị trộn. Để dễ xem xét, đóng gói và clean build, nên cấu hình cả hai nơi riêng:

~~~bash
javac ... -s build/generated-sources -d build/classes ...
~~~

Lợi ích là rõ ràng về ownership và loại output; việc tách thư mục **không tự thay đổi ý nghĩa của generated class**.

### Thư mục có cần tồn tại trước không?

Khi dùng `-d` và `-s`, hãy **tạo root directories trước** để build ổn định, nhất là khi dùng CLI trực tiếp hoặc trên các máy có cách kiểm tra đường dẫn khác nhau. Compiler/processor có thể tạo package subdirectories bên dưới root khi ghi files.

Nếu path không có quyền ghi, trỏ nhầm file thay vì directory, hoặc bị công cụ khác chiếm dụng, build có thể báo lỗi IO/Filer. Đừng coi việc một thư mục chưa tồn tại là bằng chứng processor chưa chạy: cần xem compiler logs và cấu hình output.

## 8. Các tùy chọn liên quan đến processor

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-processor demo.GreetingProcessor` | Chỉ rõ processor class cần chạy |
| `-processorpath PATH` hoặc `--processor-path PATH` | Chỉ đường tìm processor và dependencies của processor |
| `--processor-module-path PATH` | Chỉ đường tìm processors đóng gói thành module, theo quy tắc module-aware |
| `-proc:only` | Chỉ xử lý annotations; không compile class bình thường |
| `-proc:none` | Không chạy annotation processing |
| `-s DIR` | Source output location |
| `-d DIR` | Class output location |
| `-Akey=value` | Truyền option riêng tới processor nếu processor khai báo/hỗ trợ |
| `-XprintRounds` | In thông tin các processing rounds để debug |
| `-XprintProcessorInfo` | In thông tin processors được gọi và annotations mà chúng xử lý |

Các option `-X...` là lựa chọn quan sát của `javac`, không nên viết test dựa vào thông điệp/định dạng log cố định. Với annotation processor package là `demo`, phần **processorpath** phải cung cấp cả processor class và types mà processor cần load. Trong ví dụ, `AutoInfo.class` và `GreetingProcessor.class` cùng ở `build/processor-classes`.

### Chẩn đoán rounds của ví dụ

~~~bash
javac --release 17 -cp build/processor-classes -processorpath build/processor-classes -processor demo.GreetingProcessor -XprintRounds -XprintProcessorInfo -s build/generated-sources -d build/classes app-src/demo/Request.java app-src/demo/App.java
~~~

Đây là lệnh compile thực tế kèm **diagnostic output**, không phải một chương trình mới. `javac` có thể in những dòng về `Round 1`, `Round 2`, tên annotations/processors và round kết thúc. Phần log có thể nằm trên stderr và **không nên coi là stdout của `demo.App`**.

Khi debug, nên xem ba điều: processor có được gọi không, `Request` có được nhìn thấy cùng `@AutoInfo` không, và generated file đã được đặt trong `SOURCE_OUTPUT` chưa. Nếu processor không được chạy, `-s` trống là kết quả hoàn toàn có thể xảy ra.

## 9. `Filer` phân loại source, class và tài nguyên

Trong annotation processor, các API thường gặp:

| API | Dạng artifact | Location tiêu biểu |
| --- | --- | --- |
| `Filer.createSourceFile("demo.NewType")` | `demo/NewType.java` | `SOURCE_OUTPUT` → `-s` |
| `Filer.createClassFile("demo.NewType")` | `demo/NewType.class` | `CLASS_OUTPUT` → `-d` |
| `Filer.createResource(StandardLocation.CLASS_OUTPUT, "demo", "info.txt")` | `demo/info.txt` | `CLASS_OUTPUT` → `-d` |
| `Filer.createResource(StandardLocation.SOURCE_OUTPUT, "demo", "info.txt")` | `demo/info.txt` | `SOURCE_OUTPUT` → `-s` |

Processor có thể sinh **resources** ngoài Java source; do đó `-s` không nhất thiết chỉ chứa `.java`, và `-d` không nhất thiết chỉ chứa `.class`. Khi processor tạo binary trực tiếp bằng `createClassFile`, đó không phải một vòng “generated .java rồi compiler tự compile”, vì processor đang cung cấp class file.

`Filer` còn quản lý **mối quan hệ với originating elements** khi được cung cấp trong `createSourceFile(name, originatingElements...)`. Thông tin này có thể giúp tooling/build incremental hiểu generated files liên quan tới declarations nào. Ví dụ đơn giản phía trên không cần originating element, nhưng processor thực tế nên truyền những elements gốc thích hợp khi có thể.

**Không sửa generated source bằng tay rồi coi là nguồn chân lý lâu dài.** Build lần sau có thể sinh lại file, ghi đè hoặc báo tạo trùng tùy workflow. Hãy sửa annotation/processor/template hoặc cơ chế generate, rồi clean build lại.

## 10. Phân biệt processor, annotation và ứng dụng khi bố trí classpath

Annotation processing liên quan ít nhất ba nhóm artifact:

1. **Annotations:** source ứng dụng cần biết `@AutoInfo` là kiểu annotation hợp lệ. Ví dụ đặt `AutoInfo.class` trên **compile classpath**.
2. **Processor implementation:** compiler cần load `GreetingProcessor.class` và dependencies của nó. Ví dụ dùng **processor path**.
3. **Ứng dụng và generated classes:** runtime cần `App.class`, `GeneratedGreeting.class` và mọi dependency được dùng lúc chạy. Ví dụ lấy từ **class output**.

Có thể khai báo một JAR vừa chứa annotations vừa chứa processor trong demo, nhưng thực tế thường tách **annotation API** và **processor implementation** để tránh đưa thư viện codegen vào runtime không cần thiết.

Một annotation có `RetentionPolicy.SOURCE` không tự làm processor trở thành runtime dependency. Ngược lại, processor có thể **sinh code phụ thuộc một thư viện runtime**, ví dụ một generated serializer gọi vào runtime APIs; khi đó cần khai báo thư viện runtime này ngoài processor path. Không suy luận “biên dịch thành công là đủ dependencies khi deploy”.

### Classpath, module path và processor module path

Với dự án JPMS, cách load processors và annotations còn phụ thuộc chúng được đóng gói dưới dạng classpath JAR hay named modules. `--processor-module-path` là lựa chọn dành cho processors trong module path; nó khác với `--module-path` của ứng dụng và khác với `--module-source-path` vốn chỉ module source roots. Không nhập nhằng các loại đường dẫn chỉ vì chúng đều chứa tên “module”.

## 11. Generated source và các chế độ incremental build

Khi build tool như Maven hoặc Gradle điều phối Java compilation, nó thường thiết lập generated-source directory và class directory riêng, quản lý task dependencies và caching. Tên thư mục thực tế tùy plugin/config, không nhất thiết giống `build/generated-sources` hay `build/classes` trong demo CLI.

Đối với **incremental build**, cần phân biệt:

- **Nguồn viết tay**: được quản lý trong source tree của dự án, review và version control như mã nguồn bình thường.
- **Generated source**: có nguồn gốc từ processor, annotation và input model; thường được tái tạo, có thể làm mất các thay đổi thủ công.
- **Compiled classes**: sản phẩm của compilation, dùng khi chạy và packaging. Xóa class output không đồng nghĩa đã xóa generated-source output, và ngược lại.
- **Stale artifacts**: file sinh hoặc class cũ còn lại khi annotation bị xóa, processor đổi output hoặc build không clean. Chúng có thể làm IDE, tests và production build nhìn thấy các phiên bản khác nhau.

### Tình huống dễ gặp: source cũ vẫn tồn tại

Lần 1, `@AutoInfo` làm processor sinh `GeneratedGreeting.java` và `GeneratedGreeting.class`. Lần 2, người lập trình bỏ annotation khỏi `Request` nhưng không clean thư mục generated sources/classes. Khi đó file cũ có thể vẫn nằm trên disk, gây hiểu nhầm rằng processor vẫn sinh nó.

**Cách chẩn đoán:** dùng các output directories mới rỗng, compile lại và kiểm tra kết quả; hoặc dùng clean task chính thức của build system. Đừng tự động xóa cả các thư mục dự án khác nếu chưa xác định quyền sở hữu và vị trí output.

### Có nên thêm generated source directory thành source root để compile lại?

Với **một lần compile bình thường**, khi processor sinh qua `Filer`, `javac` đã biết source mới và có thể compile nó. Việc thêm `build/generated-sources` lại thành input root ngay trong cùng compilation hoặc chạy processor lần hai có thể:

- Compile trùng cùng class, gây `duplicate class`.
- Processor cố tạo file đã có, gặp `FilerException`.
- Trộn generated source của build cũ với source mới, gây sai lệch không dễ phát hiện.

Trong **pipeline tách hai bước**, như `-proc:only` rồi `-proc:none`, việc đưa generated sources vào lần compile tiếp theo là **có chủ đích**. Quyết định khác nhau tùy task graph; không áp dụng một kiểu cho mọi build.

## 12. Lỗi thường gặp và nguyên nhân gốc

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `-s` trống dù đã compile | Processor không được gọi; không gặp annotation; processor không sinh source | `-processor`, `-processorpath`, annotations, `-XprintRounds` |
| `package demo does not exist` hoặc không nhận `@AutoInfo` | Annotation API không có trên compile classpath/module path | Thêm `AutoInfo.class` đúng nơi compiler đọc source |
| `Annotation processor '...' not found` | Processor class/dependency không có trên processor path hoặc tên class sai | Compile processor trước, kiểm tra FQCN và path |
| `cannot find symbol: GeneratedGreeting` | Generated type chưa được tạo, bị xử lý sai package hoặc processing bị tắt | Xem `-s`, compiler diagnostics, `-proc:none` |
| `FilerException: Attempt to recreate a file for type ...` | Processor thử tạo cùng source/class nhiều lần hoặc tên xung đột input | Kiểm tra rounds, guard/idempotence, output sạch |
| `GeneratedGreeting.java` có nhưng thiếu `.class` | Đang dùng `-proc:only`; hoặc generated source compile lỗi | Xem chế độ `-proc`, compiler errors và `-d` |
| `GeneratedGreeting.class` có nhưng `.java` không ở `-s` mong đợi | Không chỉ định `-s`, output bị trộn, hoặc class được tạo trực tiếp | Kiểm tra location, processor API và lệnh javac |
| Source generation lỗi `IOException`/permission denied | Không ghi được thư mục output, path không hợp lệ | Kiểm tra quyền, root directories, filesystem |
| Source sinh đặt sai package directory | Processor truyền tên canonical/package sai hoặc tự ghi filesystem | Dùng `Filer.createSourceFile` và source `package` tương ứng |
| Class tồn tại trên máy nhưng thiếu khi deploy | Đóng gói không gồm generated class hoặc runtime dependency | Kiểm tra build/classes, JAR contents và classpath/module path |
| Sau sửa annotation vẫn chạy bản cũ | Stale source/class artifacts | Clean build, kiểm tra task graph và inputs |
| Ghi nguồn sinh vào thư mục source viết tay | Cấu hình `-s` sai | Tách generated sources khỏi version-controlled source |

### Một nguyên tắc debug hiệu quả

Không chỉ hỏi “đã có file `.java` chưa?”, mà hỏi tuần tự:

1. Compiler đã **tìm và chạy processor** chưa?
2. Processor có thấy đúng annotation/element và **gọi `Filer.createSourceFile`** không?
3. File nguồn có nằm tại **`-s` + đường dẫn package** không?
4. Compiler có xử lý source mới và thành công không?
5. Class file có nằm tại **`-d` + đường dẫn package** không?
6. Class file và runtime dependencies đã nằm trên classpath/module path của ứng dụng chưa?

Trả lời sáu câu này thường xác định đúng vị trí lỗi trong pipeline thay vì “thêm đường dẫn” một cách thử-và-sai.

## 13. Bảng tình huống: `-s`, `-d` và `-proc`

| Lệnh/điều kiện | Generated `.java` | Compiled `.class` |
| --- | --- | --- |
| `-processor ... -s GEN -d CLASSES` với processor sinh source hợp lệ | Trong `GEN` | Trong `CLASSES` (source thường + generated source) |
| `-processor ... -proc:only -s GEN -d CLASSES` | Trong `GEN` | Không compile app classes thông thường |
| `-proc:none -s GEN -d CLASSES` | Không sinh bằng annotation processing | Compiler có thể sinh class từ các input source đã có, nếu không lỗi |
| Có processor nhưng không chỉ định `-s`, có `-d CLASSES` | Thông thường trong class output location `CLASSES` | Trong `CLASSES` |
| Không có processor hoặc processor không tạo source | Không có generated source | Vẫn có thể sinh class cho source gốc |
| Processor chỉ tạo resource tại `CLASS_OUTPUT` | Có thể không có generated `.java` | Resource ở class output; các class thường do compiler tạo nếu compile thành công |

`-s` và `-d` là **địa điểm output**, không phải công tắc tạo ra file và không phải cam kết compilation đã thành công. Hãy đọc đầy đủ compiler diagnostics và exit code.

## 14. Checklist thực hành

- [ ] Processor đã được biên dịch, với `@SupportedAnnotationTypes` đúng tên?
- [ ] Source ứng dụng nhìn thấy annotation API trên compile classpath/module path?
- [ ] Processor implementation và dependencies nằm trên `-processorpath` hoặc `--processor-module-path` thích hợp?
- [ ] Nếu muốn chắc chắn processor chạy, đã đặt `-processor` hoặc cấu hình discovery rõ ràng?
- [ ] `-s` trỏ tới **generated source root** và `-d` tới **class output root** riêng?
- [ ] Package declaration và tên canonical truyền vào `createSourceFile` khớp nhau?
- [ ] Processor không tạo lại cùng file nhiều round hoặc trùng source gốc?
- [ ] Đang compile bình thường, `-proc:only` hay `-proc:none` theo đúng ý định?
- [ ] Khi dùng `-proc:only`, bước compile tiếp theo có lấy generated source đúng không?
- [ ] Runtime classpath/module path có **generated `.class`** chứ không chỉ `.java`?
- [ ] Có clean build khi cần để loại stale generated code/classes?
- [ ] Đã tránh sửa bằng tay các file generated vốn sẽ được tái tạo?

## 15. Câu hỏi tự kiểm tra

**1. `javac -s gen -d classes` có luôn tạo file Java trong `gen` không?**  
Không. `-s` chỉ chỉ định vị trí, processor phải sinh source mới thì mới có file.

**2. Vì sao cùng một type có `gen/demo/T.java` và `classes/demo/T.class`?**  
`.java` là source do processor tạo; `.class` là bytecode được compiler sinh sau khi biên dịch source đó.

**3. Có cần `javac` lần hai sau khi processor tạo source không?**  
Không trong chế độ compile bình thường khi source được tạo qua `Filer` và compiler tự xử lý. Có trong pipeline chủ động tách `-proc:only` rồi `-proc:none`.

**4. `-proc:only` tạo gì?**  
Chạy annotation processing và có thể ghi generated sources/resources; không sinh class files ứng dụng bằng compilation thông thường.

**5. `-proc:none` nghĩa là gì?**  
Không thực thi annotation processors; compiler vẫn có thể compile những source files được cung cấp nếu chúng đủ dependency.

**6. `-processorpath` thay `-cp` được không?**  
Không trong mọi trường hợp. Processor path cho compiler load processor; compile classpath cho source nhìn thấy annotation API và dependencies của source. Có thể trùng đường dẫn trong demo nhưng là hai trách nhiệm khác nhau.

**7. Vì sao `Generated.java` nằm dưới `gen/demo/`?**  
Tên canonical `demo.Generated` có package `demo`, nên `Filer` dùng đường dẫn package phù hợp dưới source output root.

**8. Chạy `java -cp build/generated-sources demo.App` có đúng không?**  
Không trong ví dụ. JVM cần class files và runtime dependencies, không dùng source output directory như compiled classpath.

**9. Processor sinh source sai cú pháp thì sao?**  
Có thể thấy file ở `-s`, nhưng compilation sẽ báo lỗi và class output không hoàn chỉnh.

**10. Vì sao file generated có thể xuất hiện từ lần build trước dù annotation không còn?**  
Output chưa được clean hoặc build incremental không theo dõi đúng inputs; kiểm tra bằng output directory mới và build sạch.

## 16. Tài liệu tham khảo

- [Oracle JDK 17 — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-s`, `-d`, `-processor`, `-processorpath`, `-proc:only` và `-proc:none`.
- [Java 17 API — `javax.annotation.processing.Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): source/class/resource creation và quy tắc output.
- [Java 17 API — `javax.annotation.processing.RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): elements của từng processing round.
- [Java 17 API — `javax.tools.StandardLocation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardLocation.html): `SOURCE_OUTPUT` và `CLASS_OUTPUT`.

**Kết luận:** `-s` quyết định **nguồn do processor sinh đi đâu**, `-d` quyết định **class files được đặt ở đâu**. Một generated Java source có thể tiếp tục được compiler xử lý ngay trong cùng compilation để tạo class file; chỉ khi cố ý chọn `-proc:only` mới tách bước sinh mã và bước compile classes. Cấu hình rõ ràng, dùng `Filer`, phân biệt các output roots và clean build khi cần giúp pipeline annotation processing dễ kiểm tra và đáng tin cậy.
