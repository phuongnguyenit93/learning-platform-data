# Dùng -proc để chọn chế độ annotation processing theo JDK đang sử dụng

**Annotation processing** là bước mà trình biên dịch Java có thể thực thi các **annotation processor** để đọc annotation, kiểm tra quy ước mã nguồn, phát diagnostic hoặc sinh thêm tệp nguồn. Với **javac**, tùy chọn **-proc** quyết định compiler chỉ biên dịch, chỉ chạy annotation processing, hay thực hiện cả hai.

Điểm dễ sai nhất là **chính sách mặc định đã thay đổi theo phiên bản JDK**. Một lệnh không khai báo cấu hình processor có thể tự chạy annotation processor ở JDK cũ nhưng không làm như vậy trên JDK 23+. Vì thế, khi dự án đột ngột thiếu mã được sinh ra sau khi nâng JDK, cần kiểm tra **javac thực sự chạy phiên bản nào** và **chính xác những tùy chọn nào đã được truyền vào lần biên dịch**.

Bài này tập trung vào ba chế độ **-proc:none**, **-proc:only**, **-proc:full**, sự khác nhau của mặc định theo JDK, cách tìm processor, ví dụ tự biên dịch được, chiến lược nâng cấp build và các lỗi thường gặp.

## 1. Trước hết: annotation khác với annotation processor

Một annotation là metadata trong nguồn Java, ví dụ:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
public @interface Mark {
}
~~~

Chỉ viết hoặc sử dụng **@Mark** không có nghĩa một chương trình nào đó tự chạy. Compiler có thể xử lý cú pháp và kiểu của annotation như phần thông thường của Java, nhưng **annotation processing** theo API **javax.annotation.processing** là cơ chế khác: một class triển khai giao diện **Processor** (thường kế thừa **AbstractProcessor**) được javac nạp và gọi trong các vòng xử lý.

Processor có thể:

- Đọc thông tin kiểu, khai báo và annotation bằng **javax.lang.model**.
- Phát cảnh báo hoặc lỗi qua **Messager**.
- Sinh mã nguồn mới bằng **Filer**; mã được sinh có thể được đưa vào các vòng biên dịch tiếp theo.
- Sinh tệp tài nguyên hoặc metadata theo contract của processor.
- Kiểm tra quy ước build như annotation bắt buộc trên một loại class.

Ví dụ công cụ annotation processing có thể sinh implementation của một mapper hoặc các lớp liên quan đến dữ liệu. Điều này hoàn toàn khác với reflection lúc runtime: processor chạy **trong quá trình build**, trước khi chương trình cuối cùng được chạy bằng lệnh **java**.

**Lưu ý:** annotation có retention RUNTIME không đồng nghĩa luôn có annotation processor. Và annotation có retention SOURCE vẫn có thể được processor đọc khi javac đang biên dịch nguồn. Chế độ **-proc:none** không xóa annotation khỏi source và không vô hiệu mọi kiểm tra ngôn ngữ liên quan annotation; nó chỉ **không thực hiện annotation processing do processor chạy**.

## 2. Ba giá trị của -proc

Cú pháp chuẩn của javac:

~~~bash
javac -proc:none ...
javac -proc:only ...
javac -proc:full ...
~~~

Dấu **hai chấm** là một phần của tên tùy chọn: dùng **-proc:full**, không tự thay bằng **-proc full** hay **--proc=full**. Trước khi sử dụng một giá trị, xác nhận JDK cụ thể hỗ trợ bằng **javac --help**.

| Chế độ | Chạy annotation processor? | Biên dịch source thành class file? | Tình huống |
| --- | --- | --- | --- |
| **-proc:none** | Không | Có, khi mã hợp lệ mà không cần nguồn do processor sinh | Cố ý tắt processors; kiểm tra riêng code; build không dùng processors |
| **-proc:only** | Có, khi processor được tìm thấy và có công việc phù hợp | **Không** thực hiện biên dịch cuối cùng để xuất class của các source đang xử lý | Kiểm tra annotation, thử processor, sinh nguồn trước một bước build khác |
| **-proc:full** | Có, khi có processor khả dụng | Có, bao gồm biên dịch phù hợp của source gốc và generated source | Build cần processor rồi cần artifact chạy được |

**-proc:full không bắt buộc có annotation trên mọi class** và không tự tải processor từ mạng. Nếu cấu hình không có processor nào để thực thi, lệnh vẫn có thể biên dịch bình thường nhưng không có tác dụng sinh mã. **-proc:only** cũng không có ý nghĩa bảo đảm sẽ tạo file: processor có thể chỉ kiểm tra và báo note, hoặc không phát sinh nội dung nào.

### 2.1. -proc:none: biên dịch không chạy processor

~~~bash
javac -proc:none -d out src/demo/App.java
~~~

Khi nguồn đầy đủ và các dependency cần thiết đã có, javac vẫn phân tích, kiểm tra và sinh **.class**. Điều bị tắt là lời gọi vào các annotation processors. Nếu mã nguồn tham chiếu class **chỉ được sinh bởi processor** mà class đó chưa có sẵn, việc biên dịch có thể thất bại với lỗi như **cannot find symbol**. Đây là kết quả mong đợi khi tắt bước sinh mã cần thiết.

### 2.2. -proc:only: chạy processor mà không xuất class cuối cùng

~~~bash
javac -proc:only -processor demo.MarkProcessor ...
~~~

Dùng khi muốn xác minh processor phát diagnostic hoặc sinh mã như dự kiến mà chưa bước sang compilation cuối cùng. Nếu processor dùng **Filer**, các source/resource được tạo vẫn có thể xuất hiện tùy cách cấu hình **-s** hoặc output; **-proc:only không có nghĩa không tạo bất kỳ file nào**. Điều nó loại bỏ là **bước compile source thành class files sau annotation processing**.

Không gọi **java demo.App** chỉ dựa trên một lệnh **-proc:only** trong thư mục output mới. Muốn chạy, cần có lần biên dịch đầy đủ tạo class file.

### 2.3. -proc:full: processor và biên dịch

~~~bash
javac -proc:full -processor demo.MarkProcessor ...
~~~

Chế độ này khớp chu trình thông dụng: javac tìm hoặc sử dụng processor đã chỉ định, thực hiện các vòng xử lý và sau đó biên dịch source gốc cùng source được sinh (nếu có), ghi class files vào thư mục được chọn với **-d**.

**Phân biệt phiên bản:** giá trị tường minh **-proc:full** được đưa vào các dòng JDK mới và có bản vá backport cho một số JDK cũ. **Không được mặc định mọi bản JDK 17.0.x ban đầu đều nhận -proc:full.** Phần tiếp theo cung cấp bảng version để chọn chính xác.

## 3. Mặc định theo phiên bản: điểm mấu chốt của bài

**Không có tùy chọn -proc** không phải lúc nào cũng đồng nghĩa cùng một chính sách.

| Phiên bản javac | Khi không có lựa chọn cấu hình annotation processing tường minh | Cách thực hành nên chọn |
| --- | --- | --- |
| **JDK 8–20** | Chính sách cũ: có thể phát hiện và chạy processors trên classpath theo mặc định | Muốn tắt: **-proc:none**; muốn xử lý: chọn **-processor**/processor path hoặc cơ chế mà bản JDK hỗ trợ |
| **JDK 21–22** | Tài liệu javac phát hành mô tả mặc định xử lý annotations khi tìm thấy processor; một số bản in note cảnh báo về thay đổi sắp tới | Khai báo processor cụ thể, processor path, hoặc **-proc:full** thay vì dựa vào ngầm định |
| **JDK 23+** | **Không tự quét và chạy processors chỉ vì chúng xuất hiện trên classpath**; cần yêu cầu hoặc cấu hình processing rõ ràng | Cấu hình **-processor**, **--processor-path**, **--processor-module-path** hoặc **-proc:only/full** |

Theo thông báo thay đổi chính thức cho **JDK 23**, javac ngừng việc chủ động chạy annotation processors được phát hiện ngẫu nhiên trên classpath nếu người dùng không cung cấp một tùy chọn liên quan đến annotation processing. Điều này làm các bản build lâu năm đang phụ thuộc implicit discovery có thể thiếu mã sinh sau nâng JDK.

**JDK 21 và 22:** Javac từng phát note khi processor chạy hoàn toàn theo phát hiện ngầm, nhắc nên cấu hình tường minh. Một số bài viết/early build JDK 22 có lịch sử thử nghiệm thay đổi chính sách; khi đánh giá môi trường cụ thể hãy ưu tiên **javac --help**, bản build được cài và kết quả chạy, thay vì chỉ suy đoán từ số phiên bản lớn.

**JDK 23+ mặc định tắt implicit processing** không có nghĩa mọi lệnh không ghi **-proc:full** đều bỏ processor. Nếu người dùng truyền **-processor** hoặc một processor path/module path để bật processing tường minh, javac vẫn có thể chạy processors và biên dịch như mô tả tài liệu javac 23+.

### 3.1. -proc:full có trên bản JDK nào?

Điều cần phân biệt là **hành vi mặc định cũ** với **cú pháp -proc:full được nhận diện**:

- **-proc:none** và **-proc:only** đã tồn tại từ thời Java 6.
- **-proc:full** có trên **JDK 21+** và đã được backport trong các bản cập nhật bảo mật, nổi bật gồm **JDK 17.0.11+**, **11.0.23+** của các bản phân phối OpenJDK/Oracle tương ứng.
- **JDK 17.0.0** hoặc một bản 17u chưa cập nhật không nên được giả định chấp nhận **-proc:full**. Kiểm tra **javac --help** để xác nhận thay vì suy luận chỉ theo nhãn Java 17.

Cùng dự án dùng JDK 17 bản cũ và JDK 23 có thể cần chỉnh môi trường tối thiểu trước khi dùng một cờ cấu hình thống nhất. Nếu không nâng được javac cũ, có thể chọn xử lý annotation bằng **-processor** tường minh hoặc processor path phù hợp, sau khi kiểm thử trên chính JDK đó.

### 3.2. -proc không phải --release

Ví dụ:

~~~bash
javac --release 17 -proc:full -d out ...
~~~

**--release 17** chọn mức ngôn ngữ, API nền tảng và bytecode đích. Nó **không biến javac JDK 23 thành javac JDK 17 về chính sách annotation processing**. Chính sách xử lý vẫn do **phiên bản compiler đang chạy và các tùy chọn thực tế** quyết định.

Tương tự, **java -version** cho biết runtime được gọi theo lệnh đó; cần kiểm tra thêm **javac -version** vì shell có thể tìm được các binary từ những bản cài JDK khác nhau.

## 4. Xác định đúng javac đang sử dụng

Chạy:

~~~bash
java -version
javac -version
javac --help
~~~

Nếu môi trường có nhiều JDK, xác định đường dẫn đến trình biên dịch:

~~~bash
# Linux/macOS
which javac
~~~

~~~powershell
# Windows CMD/PowerShell
where.exe javac
~~~

Những thông tin cần ghi lại:

1. **Vendor và phiên bản đầy đủ** của JDK, ví dụ 17.0.11, 21.0.x hoặc 24.0.x.
2. **Các giá trị -proc được hỗ trợ** trong javac --help.
3. **Compile command thực tế** do IDE/Maven/Gradle truyền tới javac, đặc biệt -processor, processor path và -proc.
4. **Classpath/module path của processors** và của source cần biên dịch.
5. **Kết quả sinh class/source** trong thư mục build sạch.

Lệnh chạy ngoài terminal không nhất thiết giống JDK toolchain mà Gradle hoặc Maven đang dùng; trong CI có thể có một JDK riêng cho bước compile.

## 5. Chọn processor: -processor, --processor-path và classpath

**-proc** chọn *chế độ thực thi*. Những tùy chọn sau giúp javac tìm *processor nào*:

| Tùy chọn | Vai trò |
| --- | --- |
| **-processor com.example.MyProcessor** | Chỉ định tên class processor cần chạy, thay vì phụ thuộc tự động phát hiện |
| **--processor-path path** hoặc **-processorpath path** | Chỉ nơi tìm annotation processors trên đường dẫn kiểu classpath |
| **--processor-module-path path** | Tìm annotation processors được đóng gói thành module theo JPMS |
| **-cp path** | Classpath phục vụ việc compile source; ở một số cấu hình còn được tìm processors nếu không có processor path riêng |
| **-Akey=value** | Truyền option cho processor; **không phải chỉ thị thay thế việc chọn một processor** |
| **-d out** | Thư mục class output |
| **-s generated-sources** | Thư mục nhận source được processor sinh bằng Filer |

**Một processor JAR nằm trong classpath chưa có nghĩa processor tự chạy trên JDK 23+.** Cần có lựa chọn kích hoạt tường minh. Với build hiện đại, nên ưu tiên **processor path riêng** và chỉ định rõ processors đáng tin cậy.

### 5.1. Hai phương thức khám phá processor

**Chỉ định trực tiếp:**

~~~bash
javac -processor com.example.MyProcessor --processor-path processor.jar ...
~~~

Cách này yêu cầu class **com.example.MyProcessor** tồn tại và thực thi được trên processor path. Đây là lựa chọn có tính chủ đích cao, thích hợp khi biết chính xác processor cần chạy.

**Khám phá qua service provider:**

Một JAR có thể chứa tệp:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung có thể là tên đầy đủ của processor class, một tên mỗi dòng:

~~~text
com.example.MyProcessor
~~~

Khi processing được kích hoạt và processor nằm trên đường tìm phù hợp, javac có thể tìm qua service-provider configuration này. Với JDK 23+, **cấu hình --processor-path** là một trong những cách kích hoạt rõ ràng việc xử lý; chỉ có tệp service trong dependency classpath mà không có tùy chọn kích hoạt thì không đủ.

**Lưu ý bảo mật:** Annotation processor là mã Java được thực thi trong quá trình build, không chỉ metadata được kiểm tra tĩnh. Không tùy tiện thêm JAR không đáng tin vào đường tìm processor. Thay đổi mặc định ở JDK 23 giúp tránh việc compiler bất ngờ chạy processor có mặt ở classpath khi người dùng chưa chủ động yêu cầu.

### 5.2. Processor path khác đường tìm class của ứng dụng

Một processor có thể cần được nạp từ **processor-classes** hoặc **processor.jar**, trong khi source của ứng dụng lại cần annotation type và dependency khác trên **compile classpath**.

Trong một ví dụ nhỏ, cả hai có thể trỏ đến cùng một thư mục để dễ học. Trong dự án thực tế, tách riêng processor dependency khỏi runtime dependency sẽ tránh đưa implementation của processor vào chương trình cuối không cần thiết.

Sử dụng named module còn có **--processor-module-path**, yêu cầu module processor phù hợp với cơ chế service/provider của JPMS. Không lấy ví dụ classpath ngắn ở dưới làm mô hình duy nhất cho module build.

## 6. Ví dụ hoàn chỉnh: quan sát -proc:none, -proc:only, -proc:full

Bộ ví dụ này có thể biên dịch trên **JDK 21+** và những bản **JDK 17 có cập nhật hỗ trợ -proc:full**. Ví dụ dùng **--release 17** để tránh cảnh báo phiên bản nguồn từ processor. Nó không dựa vào processor bên ngoài hoặc IDE.

Chúng ta tạo:

- Annotation **@Mark**.
- Processor **MarkProcessor**, in một **NOTE** khi thấy @Mark.
- Ứng dụng **App**, bình thường in một dòng khi chạy.
- Hai lớp output độc lập: thư mục biên dịch processor và thư mục biên dịch ứng dụng.

### 6.1. Cấu trúc tệp

~~~text
demo/
└── src/
    └── demo/
        ├── Mark.java
        ├── MarkProcessor.java
        └── App.java
~~~

Từ thư mục **demo**, tạo các file dưới đây.

**src/demo/Mark.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
public @interface Mark {
}
~~~

**src/demo/MarkProcessor.java**

~~~java
package demo;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.Mark")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class MarkProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (!annotations.isEmpty()) {
            processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE, "PROCESSOR_RAN"
            );
        }
        return false;
    }
}
~~~

Điểm chú ý:

- **AbstractProcessor** cung cấp các thành phần cơ sở cho annotation processor.
- **@SupportedAnnotationTypes("demo.Mark")** cho javac biết annotation type processor hỗ trợ.
- **@SupportedSourceVersion(RELEASE_17)** nêu mức source processor được thiết kế để xử lý. Trong ví dụ, lệnh javac biên dịch source ứng dụng với **--release 17**.
- **process(...)** có thể được gọi qua nhiều rounds; điều kiện **!annotations.isEmpty()** chỉ phát NOTE khi có annotation phù hợp trong round, tránh in thông điệp ở final round không có annotation.
- **return false** nói processor không claim độc quyền các annotation này. Điều đó không ảnh hưởng quan sát ba chế độ của ví dụ.

**src/demo/App.java**

~~~java
package demo;

@Mark
public class App {
    public static void main(String[] args) {
        System.out.println("APP_RAN");
    }
}
~~~

### 6.2. Biên dịch annotation và processor trước

Từ thư mục demo:

~~~bash
javac --release 17 -d processor-classes src/demo/Mark.java src/demo/MarkProcessor.java
~~~

Sau lệnh này, thư mục **processor-classes** có **demo/Mark.class** và **demo/MarkProcessor.class**. Không có service metadata trong ví dụ này; chúng ta sẽ dùng **-processor demo.MarkProcessor** để chọn processor bằng tên trực tiếp.

**Vì sao cần hai bước?** Compiler phải tìm và nạp được processor đã biên dịch trước khi dùng nó để xử lý một source file khác. Bài thực hành cố ý tách bước build processor khỏi bước build App để làm rõ đường đi.

### 6.3. Chế độ none: không chạy processor, vẫn biên dịch App

Trên thư mục output sạch:

~~~bash
javac --release 17 -proc:none -cp processor-classes -processorpath processor-classes -processor demo.MarkProcessor -d out-none src/demo/App.java
~~~

Trong lệnh này:

- **-cp processor-classes** giúp App nhìn thấy annotation **demo.Mark**.
- **-processorpath processor-classes** cho phép javac tìm implementation của processor.
- **-processor demo.MarkProcessor** ghi rõ tên processor.
- Nhưng **-proc:none** có hiệu lực tắt annotation processing.

Kết quả:

- **Không xuất NOTE PROCESSOR_RAN**.
- **Có out-none/demo/App.class**.
- Có thể chạy ứng dụng:

~~~bash
java -cp out-none demo.App
~~~

**Standard output:**

~~~text
APP_RAN
~~~

Việc **-processor** xuất hiện trong lệnh không biến **-proc:none** thành processing đầy đủ. Đây là chế độ cố ý không chạy processor.

### 6.4. Chế độ only: chạy processor, không biên dịch App.class

Dùng một thư mục output mới hoàn toàn trống:

~~~bash
javac --release 17 -proc:only -cp processor-classes -processorpath processor-classes -processor demo.MarkProcessor -d out-only src/demo/App.java
~~~

Trong ví dụ, compiler phát thông tin:

~~~text
Note: PROCESSOR_RAN
~~~

Đây là **diagnostic output của javac**, không phải stdout của ứng dụng App (App chưa chạy). Sau lệnh, **out-only/demo/App.class không được tạo** từ lần biên dịch này. Nếu processor này có sử dụng **Filer** để sinh source/resource thì vẫn có thể có đầu ra phù hợp; trong ví dụ hiện tại processor chỉ ghi NOTE nên không sinh file nào.

Không chạy **java -cp out-only demo.App** và kỳ vọng thành công: class App chưa được tạo.

### 6.5. Chế độ full: chạy processor rồi biên dịch

~~~bash
javac --release 17 -proc:full -cp processor-classes -processorpath processor-classes -processor demo.MarkProcessor -d out-full src/demo/App.java
~~~

Lần này:

- Javac phát **Note: PROCESSOR_RAN**.
- Javac sinh **out-full/demo/App.class**.
- Có thể chạy ứng dụng bằng:

~~~bash
java -cp out-full demo.App
~~~

Stdout:

~~~text
APP_RAN
~~~

Bảng kết quả của ba lượt thử, giả định các thư mục output ban đầu sạch:

| Lệnh | Có NOTE PROCESSOR_RAN? | Có App.class? | Chạy App được? |
| --- | --- | --- | --- |
| **-proc:none** | Không | Có | Có |
| **-proc:only** | Có | Không | Không, nếu chưa có class từ lần build khác |
| **-proc:full** | Có | Có | Có |

**Đã kiểm tra thực tế trên JDK 21** với ba lệnh sử dụng **--release 17**: none hoàn tất và sinh App.class; only in NOTE và không sinh App.class; full in NOTE và sinh App.class. Đây là bộ kiểm chứng cho chính sự khác biệt mà -proc tạo ra.

### 6.6. Tránh kết luận sai khi có class file cũ

Nếu chạy nhiều lần vào **cùng một thư mục out** mà không dọn trước, có thể còn **App.class** do lượt full trước đó tạo ra. Khi đó sau **-proc:only**, việc thấy App.class trong thư mục không chứng minh only đã tạo class.

Để kiểm chứng công bằng, dùng **out-none**, **out-only**, **out-full** riêng như các lệnh trên, hoặc xóa **chỉ thư mục output của thử nghiệm** trước mỗi lần. Không chạy thao tác dọn vào thư mục project hoặc build khác một cách bất cẩn.

## 7. Ví dụ khi processor thực sự sinh mã

Processor trong phần 6 chỉ ghi NOTE để đầu ra dễ quan sát. Trong dự án thực, processor có thể gọi **processingEnv.getFiler().createSourceFile(...)** và ghi một class mới, ví dụ **demo.GeneratedMapper**. Khi ấy sự khác nhau đáng kể hơn:

~~~text
- proc:none
    → Processor không tạo GeneratedMapper.java.
    → Nếu source gọi GeneratedMapper mà chưa có class/source từ trước:
      javac báo cannot find symbol.

- proc:only
    → Processor có thể tạo GeneratedMapper.java trong output source (-s).
    → Không làm bước biên dịch cuối cùng sinh toàn bộ class files.

- proc:full
    → Processor sinh GeneratedMapper.java qua vòng xử lý.
    → Javac tiếp tục biên dịch nguồn gốc và mã được sinh khi hợp lệ.
~~~

**Đây là sơ đồ khái niệm**, không phải stdout của một chương trình hoàn chỉnh. Các processor khác nhau có thể sinh **.java**, tài nguyên hoặc chỉ phát lỗi; không phải processor nào cũng sinh code.

Nếu muốn tách generated source rõ ràng, có thể dùng:

~~~bash
javac -proc:full -processor com.example.MapperProcessor --processor-path mapper-processor.jar -s generated-src -d out -cp dependency.jar src/MyService.java
~~~

Đây là **mẫu cấu hình**, các tên processor, JAR và source file là placeholder minh họa, không khẳng định tồn tại. **-s generated-src** chỉ thư mục generated source, còn **-d out** chỉ class output. Chúng có nhiệm vụ khác với **-proc**.

### 7.1. Annotation processors chạy theo rounds

Javac có thể chạy processor thành nhiều vòng:

1. Lần đầu, processor nhận các annotation có mặt trong source ban đầu.
2. Processor sinh thêm source mới nếu cần.
3. Compiler đưa source mới vào vòng xử lý kế tiếp.
4. Khi không sinh thêm source, javac có vòng cuối với tín hiệu **processingOver()**.
5. Nếu chính sách là full, phần biên dịch thích hợp tiếp tục tạo class files.

Để quan sát, javac hỗ trợ:

~~~bash
javac -XprintRounds -XprintProcessorInfo -proc:full -processor demo.MarkProcessor -cp processor-classes -processorpath processor-classes --release 17 -d out-full src/demo/App.java
~~~

Đầu ra chi tiết phụ thuộc phiên bản và processor. **-XprintRounds** và **-XprintProcessorInfo** là công cụ chẩn đoán; chúng không thay thế **-proc:full** hoặc một option kích hoạt processing trên JDK mới.

## 8. Chọn cấu hình đúng trong từng tình huống

| Tình huống | Chế độ phù hợp | Vì sao |
| --- | --- | --- |
| Dự án không có processor và muốn build dễ dự đoán | **-proc:none** | Không thực thi processor ngoài ý muốn |
| Dự án cần sinh code rồi tạo class để chạy | **-proc:full** cùng processor được cấu hình rõ | Có xử lý annotation và compilation |
| Cần kiểm tra annotation rule nhưng không cần class output | **-proc:only** | Chạy processor riêng để xem diagnostics hoặc source được tạo |
| JDK 23+ mà nguồn thiếu generated class sau nâng cấp | Cấu hình processor path / -processor hoặc **-proc:full** | Mặc định implicit discovery đã đổi |
| Muốn chỉ định processor đáng tin cậy duy nhất | **-processor** với processor path tường minh | Kiểm soát cụ thể class được thực thi |
| Muốn compile mà loại trừ bước generate do processor | **-proc:none** | Dùng để phân lập nguyên nhân hoặc build phần không phụ thuộc generation |
| Dự án vẫn dùng JDK 17 bản cũ | Kiểm tra hỗ trợ -proc:full, nâng bản vá hoặc chọn cấu hình -processor thích hợp | Không giả định mọi 17u nhận cờ full |

**Không có một lựa chọn -proc tốt nhất cho mọi dự án**. Chính sách đúng phụ thuộc: dự án có thật sự cần processor không; processor có đáng tin không; code generated được dùng khi nào; JDK nào chạy compiler; dependency được đặt ở đâu; CI có kiểm tra output sạch không.

Một lựa chọn dùng lâu dài là cấu hình processor và đường tìm processor **tường minh**, để việc nâng JDK không phụ thuộc default ngầm.

## 9. Nâng JDK 21/22 sang 23+: cách chẩn đoán lỗi thiếu generated code

Giả sử project dùng annotation processor tạo một class **UserMapperImpl**. Trước khi nâng JDK, build chạy được; sau đó javac báo:

~~~text
error: cannot find symbol
  symbol:   class UserMapperImpl
~~~

Nguyên nhân **có thể** là JDK mới không còn chạy processor ngầm. Nhưng không nên kết luận ngay chỉ vì tên class có hậu tố Impl: những nguyên nhân khác còn gồm processor JAR sai, annotation không được tìm thấy, processor báo lỗi, generate directory cũ hoặc cấu hình build loại nguồn mới.

Quy trình đúng:

1. Kiểm tra **javac -version** trong chính task đang thất bại, không chỉ lệnh java -version mở ở terminal.
2. Mở compile command thực tế, xác định có **-proc:none** không và có **-processor**, **--processor-path**, **--processor-module-path**, **-proc:only/full** không.
3. Kiểm tra processor JAR thực sự hiện diện trên **processor path**, không chỉ nằm trong compile/runtime dependencies.
4. Xác nhận processor hỗ trợ source version, annotation type và có thể được nạp.
5. Kiểm tra output generated source của một build sạch.
6. Thử kích hoạt xử lý một cách chủ đích, ví dụ dùng **-processor com.example.MyProcessor**, và biên dịch lại.
7. Chỉ kết luận đã sửa khi generated sources/classes thực sự được tạo và test chạy thành công trên đúng JDK của CI.

Nếu **-proc:only** tạo nguồn thành công nhưng chương trình vẫn không chạy, rất có thể do bạn chưa thực hiện bước compile đầy đủ (hoặc chưa compile generated source trong bước sau).

Nếu **-proc:full** mà không có source/class được tạo, kiểm tra việc processor có được load hoặc có annotation phù hợp không; **-proc:full không tự bảo đảm processor tồn tại**.

Nếu **-proc:none** biên dịch thành công nhưng ứng dụng có lẽ cần code generation, có thể đang sử dụng class file **cũ**. Hãy kiểm tra bằng clean build và quản lý riêng output để tránh che lỗi.

### 9.1. Kiểm tra Java 21/22 implicit-processing note

Trong JDK 21 và một số cấu hình thời kỳ chuyển tiếp, javac có thể in ghi chú kiểu **annotation processing is enabled because one or more processors were found on the class path**. Đây không phải một thông báo rằng mã sai, mà là dấu hiệu build **đang dựa vào chính sách tự tìm processor**.

Sửa bằng cách cấu hình **processor path và processor cần dùng**, hoặc bật processing tường minh theo phiên bản được hỗ trợ. Không nên chỉ dùng **-Xlint:-options** để giấu note rồi bỏ qua việc nâng cấp cấu hình, vì tương lai compiler có thể xử lý khác.

## 10. Maven, Gradle, IDE và Java toolchain

Trong Maven hoặc Gradle, bạn thường không gõ lệnh javac trực tiếp. Plugin/build tool thiết lập tham số compiler dựa trên dependency configuration, annotation-processor configuration và phiên bản Java toolchain.

**Gradle với Java plugin** có cấu hình dependency dành cho annotation processors:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    annotationProcessor 'org.example:demo-processor:1.0'
}
~~~

Đây chỉ là **mẫu cú pháp** với tọa độ artifact minh họa; thay bằng dependency thực và repository phù hợp. Build tool có thể truyền processor path tường minh khi thấy annotationProcessor dependency. Không coi snippet này là một ví dụ project runnable độc lập.

**Maven Compiler Plugin** có cấu hình processors, processor paths/dependencies và tùy phiên bản có thuộc tính **proc**. Phiên bản plugin và JDK quyết định CLI javac được tạo; hãy kiểm tra tài liệu plugin đang dùng. Không cho rằng **maven.compiler.proc** hoặc cấu hình processor của mọi phiên bản Maven Compiler Plugin có cùng mặc định.

**IDE** có thể bật annotation processing cho project, nhưng cách cài đặt thường khác giữa javac CLI, IntelliJ và Eclipse compiler. Kết quả chỉ thành công trong IDE mà thất bại trên CI thường có nghĩa cấu hình thực tế của hai nơi khác nhau.

### 10.1. Toolchain thay đổi chính sách compiler

Ví dụ shell dùng **javac 24**, nhưng Gradle toolchain chọn **JDK 21** cho task compileJava. Khi đó chính sách processor được xác định bởi javac/JDK thực thi task tương ứng, không bởi phiên bản java bạn vô tình mở trong terminal.

Cách kiểm tra bền vững là ghi lại **compiler command/toolchain**, **processor configuration**, **generated source output** và **build logs** của cùng một task.

## 11. Cảnh báo và lỗi hay gặp

### 11.1. “Invalid flag: -proc:full”

Một bản javac quá cũ có thể không hiểu giá trị **full**. Kiểm tra **javac -version** và **javac --help**, rồi nâng bản vá nếu có thể. Trên các bản cũ vẫn có thể hỗ trợ **-proc:none** và **-proc:only**, nhưng không có nghĩa **-proc:full** đã có.

Không sửa thành **-proc:none** để “hết lỗi option” nếu dự án cần processor. Làm vậy có thể chỉ chuyển lỗi thành mất generated classes.

### 11.2. “Annotation processor ... not found”

Javac đã được yêu cầu chạy một processor nhưng không tìm thấy class hoặc không thể nạp processor. Kiểm tra:

- Tên đầy đủ trong **-processor**.
- Nơi chứa processor class/JAR ở **-processorpath** hoặc module path phù hợp.
- Những dependency mà bản thân processor cần để khởi tạo.
- Tương thích bytecode: processor được biên dịch bằng JDK mới hơn có thể không nạp được trên JVM cũ chạy javac.
- Với JPMS: provider declaration và module visibility.

**Không giải quyết bằng việc chỉ thêm import trong source ứng dụng**. Import phục vụ tham chiếu type của ứng dụng, còn nạp processor xảy ra trong compiler environment.

### 11.3. Processor chạy nhưng không có class file

Nếu đang dùng **-proc:only**, đây là **hành vi thiết kế**. Nếu mong muốn class output, đổi sang **-proc:full** hoặc chạy bước biên dịch tiếp theo.

Nếu đang dùng full, kiểm tra lỗi compiler, đường **-d**, output từ vòng generated sources và việc compilation hoàn tất. Đừng kết luận chỉ bằng sự tồn tại của một tệp .java generated.

### 11.4. Không thấy processor chạy trên JDK 23+

Kiểm tra invocation có **ít nhất một lựa chọn kích hoạt processing phù hợp**. Việc processor chỉ xuất hiện trên classpath không còn đủ nếu không có option yêu cầu. Cấu hình **-processor** rõ tên cùng đường tìm processor là cách dễ kiểm tra nhất.

### 11.5. “Supported source version ... less than -source ...”

Processor khai báo mức source được hỗ trợ thấp hơn compilation target có thể phát warning. Trong ví dụ, annotation processor khai báo **RELEASE_17**, nên câu lệnh **--release 17** làm các kết quả dễ đối chiếu. Trong project Java 21/25, cập nhật processor để hỗ trợ source level thích hợp thay vì luôn hạ **--release** chỉ để tránh warning.

### 11.6. Không có processor nào thực thi dù đã có -proc:full

Khi **-proc:full** mà classpath không chứa processor có thể được tìm thấy (hoặc processor bị chọn sai), javac có thể vẫn compile code thường mà không có bất kỳ processor nào thực sự chạy. Hãy dùng **-processor** để chọn rõ và thử **-XprintProcessorInfo** khi cần chẩn đoán.

## 12. Checklist để cấu hình một lần, dùng ổn định

Trước khi chấp nhận cấu hình annotation processing cho build chính:

- [ ] Đã xác định **javac thực tế và bản cập nhật JDK**.
- [ ] Chọn chính sách **none / only / full** dựa trên mục đích build.
- [ ] Nếu cần processors, đã chỉ rõ **processor names hoặc processor path** đúng cách.
- [ ] Processor dependency được tách hợp lý khỏi runtime dependency.
- [ ] Không phụ thuộc ngầm vào processor xuất hiện tình cờ trên classpath.
- [ ] Source-generated và class-generated output được kiểm tra bằng **clean build**.
- [ ] Đã phân biệt **--release** với **chính sách processing của javac**.
- [ ] JDK cũ có hỗ trợ giá trị **-proc:full** hay chưa được xác minh.
- [ ] Đã chạy test trên JDK dùng ở CI và production build.
- [ ] Annotation processors và các dependency của chúng đến từ nguồn đáng tin cậy.

## 13. Bài tập thực hành

**Bài 1 — So sánh ba chế độ:** Tạo ba file ở phần 6. Chạy đầy đủ các lệnh none, only, full vào ba thư mục output riêng. Ghi lại có hay không **Note: PROCESSOR_RAN**, **App.class** và stdout khi chạy App.

**Bài 2 — Thử xóa -processor:** Trên ví dụ không có service registration, bỏ **-processor demo.MarkProcessor**. Giải thích vì sao processor có thể không được tìm thấy dù **-proc:full**. Nếu muốn discovery tự động, cần đóng gói **META-INF/services/javax.annotation.processing.Processor** tương ứng.

**Bài 3 — Kiểm tra JDK cũ:** Chạy **javac --help** trên JDK 17.0.0 và một bản 17u đã cập nhật (nếu có). So sánh việc hỗ trợ **-proc:full**; không cần chạy trên cùng một máy nếu có CI container tương ứng.

**Bài 4 — --release có ảnh hưởng default không?** Trên JDK 23+, thử **--release 17** với một processor chỉ nằm trên classpath nhưng không có lựa chọn processing. Dự đoán liệu compiler sẽ tự chạy processor chỉ vì release là 17 hay không; đối chiếu chính sách của **javac đang chạy**.

**Bài 5 — Mã generated thiếu:** Tưởng tượng một project dùng processor sinh **OrderMapperImpl**. Hãy lập checklist phân biệt lỗi cấu hình processor path, processor không hỗ trợ annotation, -proc:none và build cũ còn class file.

**Bài 6 — Kiểm soát rủi ro:** Dùng **-processor** để chỉ định một processor đã kiểm tra, so với cách dựa vào classpath scanning. Giải thích ưu điểm về tính dự đoán, khả năng audit và bảo mật.

## 14. Tự kiểm tra kiến thức

1. **-proc:none** có dừng toàn bộ compilation không?
2. Khi chạy **-proc:only**, tại sao tệp generated source vẫn có thể được tạo nhưng **App.class** của source gốc không xuất hiện?
3. **-proc:full** khác **-proc:only** tại bước nào?
4. Vì sao cấu hình chạy được ở JDK 21 nhưng thiếu mã sinh ở JDK 23?
5. Chỉ có processor JAR trên compile classpath có đủ để tự chạy processor trên JDK 23+ không?
6. **-processor** khác **--processor-path** như thế nào?
7. Vì sao **--release 17** trên javac 24 không biến chính sách annotation processing thành mặc định của JDK 17?
8. Vì sao không được giả định mọi JDK 17 đều hỗ trợ cú pháp **-proc:full**?
9. Chế độ nào phù hợp để kiểm tra annotation rule mà không muốn biên dịch class files?
10. Khi một processor không chạy, bạn sẽ kiểm tra Java toolchain, classpath, service provider và lệnh javac theo thứ tự nào?

## 15. Tài liệu tham khảo chính thức

- **Oracle JDK 21 – The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Oracle JDK 22 – The javac Command:** https://docs.oracle.com/en/java/javase/22/docs/specs/man/javac.html
- **Oracle JDK 23 – The javac Command:** https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- **Oracle JDK 26 – The javac Command:** https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html
- **Oracle JDK 23 Release Notes – annotation processing disabled by default:** https://www.oracle.com/java/technologies/javase/23-relnote-issues.html
- **Inside Java/OpenJDK Quality Outreach – JDK 23 change and backports:** https://inside.java/2024/06/18/quality-heads-up/
- **Inside Java – JDK 21/22 implicit processing note:** https://inside.java/2023/07/29/quality-heads-up/
- **Java SE 21 – AbstractProcessor API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html

**Ghi nhớ:** **-proc:none** biên dịch mà không chạy annotation processor; **-proc:only** chỉ xử lý annotation; **-proc:full** vừa xử lý vừa biên dịch. Quan trọng hơn, từ **JDK 23**, annotation processing cần một yêu cầu/cấu hình rõ ràng và không còn mặc định chạy chỉ vì processor nằm trên classpath. Luôn xác minh **javac thực tế**, chọn processor đáng tin cậy, kiểm tra output sạch và đừng nhầm **--release** với lựa chọn **-proc**.