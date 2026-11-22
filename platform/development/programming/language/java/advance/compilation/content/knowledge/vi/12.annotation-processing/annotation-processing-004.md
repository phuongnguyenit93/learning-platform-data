# Processor phát hiện annotation nào và ý nghĩa claim annotation

Annotation processing là một giai đoạn có thể cắm thêm vào quá trình biên dịch Java. Khi gặp một annotation, javac không tự động chạy mọi class mang tên Processor: nó phải tìm được các **processor implementation**, biết chúng **hỗ trợ loại annotation nào**, xác định **annotation type nào có mặt trong một round**, rồi quyết định **loại nào còn được chuyển cho processor tiếp theo**. Quyết định cuối cùng được thể hiện bằng giá trị boolean của phương thức **Processor.process**: trả true nghĩa là **claim**, trả false nghĩa là **không claim**.

Bài học thuộc phần **Xử lý annotation** của Java Advance – compilation. Trọng tâm là giao thức chuẩn JSR 269 trong các package javax.annotation.processing và javax.lang.model. Các ví dụ biên dịch theo Java 17 bằng javac --release 17, đã được kiểm chứng bằng JDK 24.0.2. Cơ chế và kết quả log được mô tả theo đúng từng lượt thực nghiệm; cần chú ý những thay đổi mặc định về phát hiện processor từ JDK 23.

## 1. Ba thứ khác nhau: annotation type, annotation use và processor

**Annotation type** được khai báo bằng từ khóa @interface:

~~~java
package demo;
public @interface Flag {}
~~~

**Annotation use** là việc áp annotation type lên một phần tử của chương trình:

~~~java
package demo;
@Flag
public class Use {}
~~~

**Annotation processor** là một class triển khai giao diện javax.annotation.processing.Processor, thường kế thừa AbstractProcessor để giảm phần mã cơ sở. Nó được javac gọi để phân tích phần tử chương trình, phát chẩn đoán và/hoặc sinh thêm source hay resource trong build.

Chỉ có @Flag trên source **không bảo đảm** processor nào đó đã được phát hiện và gọi. Một annotation type có thể tồn tại mà không có processor nào; đây không tự động là lỗi biên dịch. Ngược lại, một processor có thể đã được phát hiện nhưng không được gọi vì không có annotation type phù hợp.

### 1.1. Sơ đồ lựa chọn trong một vòng

~~~text
Source, class và generated source được xem xét trong round
                          |
                          v
             Xác định annotation types hiện diện
                          |
                          v
         Tìm các processor được cấu hình/phát hiện
                          |
                          v
   So khớp với supported annotation types của từng processor
                          |
                          v
       process(Set<TypeElement>, RoundEnvironment)
                          |
                +---------+---------+
                |                   |
           return false        return true
                |                   |
       Không claim types       Claim types được nhận
                |                   |
         Processor sau có thể   Processor sau không nhận
         nhận cùng types        chính types đã được claim
                          |
                          v
        Nếu tạo thêm nguồn/class thì có thể mở round mới
~~~

**Claim theo annotation type của round**, không phải thao tác xóa annotation khỏi source, không phải thông báo thành công/thất bại và không phải lệnh dừng toàn bộ quá trình biên dịch.

## 2. Processor được javac tìm thấy bằng cách nào?

Có hai cách phổ biến: **chỉ định class processor** hoặc **service discovery**.

### 2.1. Chỉ định tường minh

~~~sh
javac -processor processor.MyProcessor -processorpath processor-classes ...
~~~

Trong đó:

- **-processor**: danh sách tên class processor đủ package; nhiều tên phân cách bởi dấu phẩy.
- **-processorpath**, còn có dạng **--processor-path**: đường tìm processor implementation và những dependency phục vụ chính processor.
- **-classpath** / **-cp**: đường tìm các kiểu mà nguồn Java ứng dụng cần để biên dịch; không nên mặc nhiên đánh đồng với processor path.

Một processor có thể cần thư viện build-only nhưng ứng dụng sau khi biên dịch không cần thư viện đó ở runtime. Vì vậy dự án thực tế thường khai báo processor dependencies riêng.

Chọn processor bằng -processor cho phép người học tái lập chính xác việc processor nào tham gia. Nó bỏ qua việc chọn tên processor qua service discovery mặc định, dù lớp được chỉ định vẫn phải được nạp thành công.

### 2.2. Service provider

Đối với processor trên classpath, có thể đăng ký bằng file bên trong JAR/thư mục processor:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Ví dụ nội dung:

~~~text
processor.FirstProcessor
processor.SecondProcessor
~~~

Khi annotation processing đã được bật và dùng service discovery, javac tìm processor nhờ metadata này trên đường tìm processor. File có tên chính xác theo giao diện javax.annotation.processing.Processor.

**JDK 23 trở lên thay đổi mặc định:** javac không tự chạy annotation processors chỉ vì một processor tình cờ nằm trên classpath mà không có cấu hình xử lý annotation nào. Phải cấu hình rõ bằng -processor, --processor-path, --processor-module-path hoặc yêu cầu -proc:full / -proc:only phù hợp. Ở các JDK cũ hơn, mặc định có thể khác. Bài này chủ động truyền -processor để không dựa vào mặc định.

### 2.3. Chế độ annotation processing

| Tùy chọn | Tác dụng |
|---|---|
| -proc:none | Tắt annotation processing, vẫn biên dịch mã nguồn |
| -proc:only | Chạy processors mà không tiếp tục bước tạo class thông thường của build |
| -proc:full | Chạy processors rồi biên dịch thông thường |
| -processor A,B | Chọn các processor có tên cụ thể thay vì dựa vào discovery |
| -processorpath path | Chỉ định nơi tìm processor implementations |
| -XprintRounds | Chẩn đoán các vòng processing |
| -XprintProcessorInfo | Chẩn đoán processor khớp annotation nào và trả claim ra sao |

Một số bản update JDK cũ hỗ trợ -proc:full khác nhau; hãy kiểm tra javac --help của compiler đang sử dụng. Tùy chọn -X phục vụ chẩn đoán, không cần bật thường trực cho mọi build.

## 3. Supported annotation types là khả năng xử lý, không phải kết quả quét

Mỗi Processor có phương thức:

~~~java
Set<String> getSupportedAnnotationTypes();
~~~

Nó mô tả **tên các annotation interface** mà processor tuyên bố hỗ trợ. Với AbstractProcessor, có thể khai báo bằng:

~~~java
@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ExampleProcessor extends AbstractProcessor {
    // Cần implement phương thức process.
}
~~~

Đoạn trên chỉ minh họa phần khai báo class, chưa phải processor chạy độc lập. AbstractProcessor có thể lấy giá trị hỗ trợ từ các annotation metadata trên class; một triển khai Processor khác cũng có thể trả tập trực tiếp từ phương thức tương ứng.

| Supported type pattern | Ý nghĩa |
|---|---|
| demo.Flag | Hỗ trợ annotation type có tên demo.Flag |
| demo.* | Hỗ trợ các annotation type phù hợp vùng tên demo theo cú pháp pattern |
| * | Universal: mọi annotation type, bao gồm cả tập rỗng |
| some.module/demo.Flag | Tên type có module prefix trong môi trường xử lý named modules |

Đừng khai báo **demo.Use** nếu ý định là xử lý **@demo.Flag** trên class Use; demo.Use là tên class được gắn annotation, không phải annotation type. Cũng đừng đưa ký tự @ vào supported type string.

Nếu hỗ trợ nhiều loại, có thể viết:

~~~java
@SupportedAnnotationTypes({
    "demo.Flag",
    "demo.OtherFlag"
})
~~~

Không có nghĩa mỗi lần process sẽ nhận đủ cả hai. Compiler chỉ chuyển **những loại thực sự xuất hiện và chưa bị claim trong round**, đồng thời thuộc tập hỗ trợ của processor.

### 3.1. Vì sao wildcard "*" cần chú ý?

Universal processor hỗ trợ "*" có thể được chọn **kể cả khi round không có annotation nào**. Điều này hữu ích cho checker chung cần kiểm tra root elements. Tuy nhiên, nếu luôn trả true, nó có thể claim mọi loại annotation có mặt và ngăn processor chuyên biệt khác được xét cho cùng types. Processor chỉ quét/audit nguồn thường nên trả false để tránh can thiệp không cần thiết.

**Supported "*"** nói processor **có thể** nhận tất cả types. **Return true** mới là hành động **claim** các types mà tool đã đề nghị processor xử lý trong lần gọi cụ thể.

## 4. Tham số annotations của process chứa gì?

Chữ ký của phương thức xử lý:

~~~java
@Override
public boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
) {
    // xử lý...
}
~~~

**annotations** chứa các đối tượng TypeElement đại diện **cho annotation types**, không phải các class/field/method đã gắn annotation. Ví dụ có 50 class được gắn @demo.Flag trong một round, tập annotations của processor chuyên xử lý Flag vẫn thường chỉ chứa **một type demo.Flag**.

Muốn tìm các phần tử đã gắn annotation, dùng RoundEnvironment:

~~~java
for (TypeElement annotationType : annotations) {
    for (Element element :
            roundEnv.getElementsAnnotatedWith(annotationType)) {
        System.out.println(element.getSimpleName());
    }
}
~~~

Đoạn trích trên cần import javax.lang.model.element.Element và đặt trong một processor hoàn chỉnh. Các element này thuộc model biên dịch, không phải các Class runtime được nạp bằng Class.forName. Class đang được biên dịch thậm chí chưa có bytecode để nạp.

**Hai phạm vi khác nhau:**

- Annotation types hiện diện trong **round**: có thể bao gồm @Target, @Retention trên chính source annotation type, cũng như @Flag trên class ứng dụng.
- Annotation types **được giao cho một processor cụ thể**: phụ thuộc supported types và việc processor trước đã claim gì.

Với processor chỉ hỗ trợ demo.Flag, log có thể cho thấy annotations = [demo.Flag] dù thông tin toàn round cho thấy cả java.lang.annotation.Target và java.lang.annotation.Retention.

## 5. Claim annotation có nghĩa chính xác là gì?

Phương thức process trả về boolean.

~~~java
return true;  // Claim annotation types được giao trong lần gọi
~~~

~~~java
return false; // Không claim; processor sau còn cơ hội nhận types đó
~~~

**True:** trong round hiện tại, những annotation types tool giao cho processor được đánh dấu **đã claim**, do đó các processor tiếp theo không được hỏi xử lý chính các loại đó như những loại còn unmatched.

**False:** những annotation types đó **vẫn unclaimed** trong round; nếu có processor khác hỗ trợ, nó **có thể** được gọi để xử lý chúng.

### 5.1. Claim không phải báo trạng thái thành công

Return true **không** đồng nghĩa compile pass. Processor có thể phát lỗi qua Messager rồi return true. Return false **không** đồng nghĩa xử lý thất bại: một validator phụ trợ có thể hoàn tất bình thường rồi return false để công cụ khác tiếp tục được chọn.

Nếu phát hiện annotation sai, dùng cơ chế chẩn đoán:

~~~java
processingEnv.getMessager().printMessage(
    javax.tools.Diagnostic.Kind.ERROR,
    "Invalid annotation usage"
);
~~~

Đây là code đặt bên trong processor; báo lỗi kiểu Diagnostic.Kind.ERROR làm compiler biết có lỗi. Boolean claim độc lập với việc phát chẩn đoán.

### 5.2. Claim không phải xóa một annotation use

Nếu các class A và B đều có @demo.Flag, processor nhận **type demo.Flag**. Không thể dùng return true để nói “claim @Flag trên A nhưng để @Flag trên B cho processor khác”. Boolean claim áp dụng ở **mức annotation type được giao trong round**, không phải từng element được gắn annotation. Logic nội bộ vẫn có thể xử lý A/B khác nhau, nhưng đó là lựa chọn của processor, không phải phạm vi của boolean.

### 5.3. Claim không kết thúc toàn bộ rounds

Một processor return true ở round 1 vẫn có thể được gọi trong round 2 nếu nguồn mới sinh ra lại mang annotation type đó. Claim có phạm vi **round hiện tại**, không phải khóa vĩnh viễn cho toàn bộ compilation.

### 5.4. Không claim không ép processor khác chạy

Return false chỉ để type còn unclaimed. Nếu không có processor khác hỗ trợ hoặc không còn processor nào đủ điều kiện, không ai được gọi thêm. Return false cũng **không** tạo round mới và không làm compiler gọi lại ngay chính processor đó với cùng type trong round hiện tại.

## 6. Thực hành Java 17: hai processor tranh quyền claim

Chúng ta tạo một annotation SOURCE và hai processor cùng hỗ trợ nó. Một processor trả true, processor kia trả false. Kết quả được quan sát trực tiếp khi đổi thứ tự trên -processor.

Cấu trúc:

~~~text
project/
├── src/demo/
│   ├── Flag.java
│   ├── Use.java
│   └── Plain.java
├── processor-src/processor/
│   ├── TrueProcessor.java
│   ├── FalseProcessor.java
│   └── StarProcessor.java
├── processor-classes/
├── out1/
├── out2/
├── out3/
└── out4/
~~~

Lưu từng class public vào đúng tên tệp được ghi. Terminal chạy tại gốc project.

### 6.1. Annotation type và nguồn ứng dụng

**src/demo/Flag.java:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Flag {
}
~~~

**src/demo/Use.java:**

~~~java
package demo;

@Flag
public class Use {
}
~~~

**src/demo/Plain.java:**

~~~java
package demo;

public class Plain {
}
~~~

RetentionPolicy.SOURCE nghĩa annotation không cần được giữ trong class file. Điều này **không ngăn** javac processor nhìn thấy annotation khi đang đọc source; khả năng xử lý annotation compile-time và khả năng truy vấn reflection ở runtime là hai việc khác nhau.

### 6.2. Processor thứ nhất: trả true

**processor-src/processor/TrueProcessor.java:**

~~~java
package processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class TrueProcessor extends AbstractProcessor {
    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "TRUE " + annotations
            + " final=" + roundEnv.processingOver()
        );
        return true;
    }
}
~~~

### 6.3. Processor thứ hai: trả false

**processor-src/processor/FalseProcessor.java:**

~~~java
package processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class FalseProcessor extends AbstractProcessor {
    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "FALSE " + annotations
            + " final=" + roundEnv.processingOver()
        );
        return false;
    }
}
~~~

Hai processor chỉ khác quyết định claim. Trong ứng dụng thực tế, process thường truy vấn elements rồi tạo code/validate; ở bài này chỉ in thông tin để thấy rõ cơ chế phối hợp.

### 6.4. Biên dịch các processors

Từ gốc project, tạo thư mục kết quả. Linux/macOS:

~~~sh
mkdir -p processor-classes out1 out2 out3 out4
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path processor-classes,out1,out2,out3,out4 | Out-Null
~~~

Biên dịch hai processor:

~~~sh
javac --release 17 -encoding UTF-8 -d processor-classes processor-src/processor/TrueProcessor.java processor-src/processor/FalseProcessor.java
~~~

Lệnh này chỉ tạo **implementation classes**, chưa dùng chúng để xử lý @Flag trong nguồn ứng dụng.

### 6.5. FalseProcessor trước TrueProcessor

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.FalseProcessor,processor.TrueProcessor -d out1 src/demo/Flag.java src/demo/Use.java
~~~

**Các dòng processor in ra đã được kiểm chứng:**

~~~text
FALSE [demo.Flag] final=false
TRUE [demo.Flag] final=false
FALSE [] final=true
TRUE [] final=true
~~~

Diễn biến:

1. Round thông thường có type demo.Flag.
2. FalseProcessor nhận [demo.Flag] và trả false, nên demo.Flag vẫn unclaimed.
3. TrueProcessor được phép nhận [demo.Flag] ở **cùng round**, trả true.
4. Khi xử lý kết thúc, cả hai processor đã tham gia được gọi trong final round với tập rỗng, processingOver() là true.

Không có vòng round mới do FalseProcessor trả false. Các dòng final thuộc vòng kết thúc, không phải bằng chứng mã bị xử lý thất bại.

### 6.6. TrueProcessor trước FalseProcessor

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.TrueProcessor,processor.FalseProcessor -d out2 src/demo/Flag.java src/demo/Use.java
~~~

**Các dòng processor in ra đã được kiểm chứng:**

~~~text
TRUE [demo.Flag] final=false
TRUE [] final=true
~~~

TrueProcessor claim demo.Flag trước. FalseProcessor không được gọi vì type cần xử lý không còn trong tập annotation unmatched khi tới lượt nó. Trong thực nghiệm này, FalseProcessor cũng không nhận final round vì nó chưa được kích hoạt.

Hai lệnh vẫn **biên dịch thành công**, bất kể claim true hay false. Đó là bằng chứng claim không phải cờ báo lỗi.

**Lưu ý về thứ tự:** chúng ta chủ động truyền danh sách -processor trong thực hành. Trong dự án dùng service discovery hoặc build tool, không nên giả định một thứ tự chưa được cam kết để tạo sự phụ thuộc giữa các processor.

## 7. Universal processor có thể chạy khi không có annotation

Tạo **processor-src/processor/StarProcessor.java**:

~~~java
package processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class StarProcessor extends AbstractProcessor {
    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "STAR " + annotations
            + " final=" + roundEnv.processingOver()
        );
        return false;
    }
}
~~~

Biên dịch:

~~~sh
javac --release 17 -encoding UTF-8 -d processor-classes processor-src/processor/StarProcessor.java
~~~

Chạy nó trên **Plain.java** không có annotation:

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.StarProcessor -d out3 src/demo/Plain.java
~~~

Kết quả:

~~~text
STAR [] final=false
STAR [] final=true
~~~

Vì StarProcessor hỗ trợ "*", tool có thể gọi nó ở **round thông thường với tập annotation rỗng**. Đây không phải lỗi. Processor có thể dùng roundEnv.getRootElements() để quét những root elements ngay cả khi annotations không có type nào.

So sánh với processor chỉ hỗ trợ Flag:

~~~sh
javac --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.FalseProcessor -d out4 src/demo/Plain.java
~~~

Khi kiểm chứng, lệnh **không in dòng FALSE**, vì round không có annotation demo.Flag để kích hoạt FalseProcessor. Phải phân biệt: một processor được gọi với tập rỗng **khác** một processor không được gọi.

Nếu đổi StarProcessor thành return true, nó có thể claim mọi annotation types được trao trong round có annotation. Checker dạng universal thường **nên return false** để tránh vô tình khiến các processor chuyên biệt không được gọi.

## 8. Rounds khi một processor tạo thêm nguồn

Annotation processing có thể chạy qua nhiều **processing rounds**. Nếu processor dùng Filer để tạo Java source chứa annotation, source mới có thể trở thành root của round kế tiếp. Đây là lý do một processor đã claim type trong round 1 vẫn có thể gặp **cùng type** ở round 2.

### 8.1. Một processor sinh thêm class @Flag

Tạo **processor-src/processor/GeneratingProcessor.java**:

~~~java
package processor;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Flag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GeneratingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv
    ) {
        System.out.println(
            "GEN types=" + annotations
            + ", last=" + roundEnv.processingOver()
        );

        if (!roundEnv.processingOver() && !generated) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                    .createSourceFile("generated.Extra");
                try (Writer writer = file.openWriter()) {
                    writer.write(
                        "package generated; "
                        + "@demo.Flag public class Extra {}"
                    );
                }
                generated = true;
            } catch (IOException ex) {
                throw new IllegalStateException(ex);
            }
        }
        return true;
    }
}
~~~

Biên dịch processor, tạo thư mục output và nguồn sinh:

~~~sh
javac --release 17 -encoding UTF-8 -d processor-classes processor-src/processor/GeneratingProcessor.java
~~~

Linux/macOS:

~~~sh
mkdir -p generated-src output
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path generated-src,output | Out-Null
~~~

Chạy từ gốc project:

~~~sh
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -processorpath processor-classes -processor processor.GeneratingProcessor -s generated-src -d output src/demo/Flag.java src/demo/Use.java
~~~

**Ba dòng do processor in ra, đã kiểm chứng:**

~~~text
GEN types=[demo.Flag], last=false
GEN types=[demo.Flag], last=false
GEN types=[], last=true
~~~

| Round | Nguồn chính được xử lý | Annotation type gửi processor | processingOver |
|---|---|---|---|
| 1 | demo.Flag và demo.Use | demo.Flag | false |
| 2 | generated.Extra do processor tạo trong round 1 | demo.Flag | false |
| 3 | Final round, không có source mới | tập rỗng | true |

Dòng thứ hai chứng minh: return true ở round 1 **không claim vĩnh viễn** demo.Flag trong mọi round. Một root mới có cùng annotation sẽ lại làm nó xuất hiện ở round kế tiếp.

Biến instance **generated** bảo đảm processor không tạo cùng một file qua nhiều vòng, tránh lỗi tạo trùng hoặc vòng sinh mã không kiểm soát. Khi dùng Filer, đừng ghi đè source gốc tùy tiện; mỗi file được tạo phải theo quy tắc Filer và đặt tên nhất quán.

### 8.2. Final round không giống tập rỗng ở round thông thường

Có hai dữ kiện riêng:

- **annotations.isEmpty()**: không có annotation type nào được giao trong lời gọi này.
- **roundEnv.processingOver()**: tool đang ở vòng kết thúc.

Một universal processor có thể nhận tập rỗng **khi processingOver là false**, như StarProcessor. Một processor đã được gọi trong vòng trước có thể nhận tập rỗng **khi processingOver là true**, như TrueProcessor hoặc GeneratingProcessor. Không thể lấy tập rỗng làm tín hiệu duy nhất rằng processing đã kết thúc.

Trong final round, không nên dựa vào việc tạo tệp mới để kích hoạt thêm vòng xử lý thông thường. Sử dụng vòng kết thúc để tổng hợp hoặc phát chẩn đoán sau khi các vòng sinh mã cần thiết đã chạy.

## 9. Claim và annotation retention là hai khái niệm tách biệt

Retention quyết định annotation được giữ tới giai đoạn nào:

| Retention | Ý nghĩa khái quát |
|---|---|
| SOURCE | Tồn tại ở source, không cần lưu trong bytecode |
| CLASS | Được lưu trong class file nhưng không bắt buộc hiện diện qua reflection runtime |
| RUNTIME | Có thể truy vấn runtime qua reflection trong điều kiện thích hợp |

Processor dùng compiler model nên xử lý SOURCE annotation được. **Claim không sửa retention**: return true không biến SOURCE thành RUNTIME, cũng không tự xóa annotation type khỏi class file.

Ví dụ @Flag của bài có SOURCE retention. Processor vẫn nhận demo.Flag và in log trong khi biên dịch. Nếu ứng dụng sau này cần reflection thấy annotation, phải khai báo RUNTIME retention thích hợp; đổi return true/false không giải quyết nhu cầu đó.

## 10. Repeatable annotations và các loại bị bỏ sót

Với repeatable annotation, một type như Tag có thể được sử dụng nhiều lần trên cùng element thông qua container annotation Tags. Theo đặc tả Processor, **annotation được bọc trong container không tự trở thành một annotation type present** chỉ bởi việc nó xuất hiện dưới container. Vì thế processor xử lý repeatable annotations nên xem xét hỗ trợ **cả type repeatable và type container**:

~~~java
@SupportedAnnotationTypes({
    "demo.Tag",
    "demo.Tags"
})
~~~

Đây chỉ là metadata minh họa; muốn chạy phải định nghĩa Tag, Tags và @Repeatable tương ứng. Không được giả định rằng viết nhiều @Tag luôn làm set annotations chứa đúng cùng tổ hợp types trong mọi hình thức source/bytecode.

Với named modules, API còn cho phép tên supported annotation type có module prefix dạng moduleName/package.Annotation để phân biệt trường hợp cần thiết. Bài thực hành cơ bản dùng unnamed module, nên demo.Flag là tên đầy đủ và đủ rõ.

## 11. Cơ chế claim không sửa mọi lỗi ngữ nghĩa

Một annotation processor có thể kiểm tra quy tắc miền và báo lỗi riêng, nhưng javac vẫn có trách nhiệm kiểm tra mã Java: kiểu, tên, truy cập, return và các ràng buộc ngôn ngữ khác.

- Return true không miễn trừ lỗi Java.
- Return false không báo compiler thất bại.
- Processor có thể tạo source mới, nhưng source đó vẫn phải được compile/kiểm tra hợp lệ.
- Processor chạy được không chứng minh mã sinh ra chạy đúng ở runtime.
- Nếu processor ném exception không được xử lý, compiler có thể dừng xử lý hoặc báo lỗi build; điều đó khác hoàn toàn với boolean claim.

Khi phát lỗi nghiệp vụ cần thiết, dùng **Messager**. Khi cần tạo source/resource, dùng **Filer**. Khi cần xác định kiểu hoặc element, dùng **Elements**, **Types**, **RoundEnvironment**. Không biến giá trị boolean của process thành bộ mã lỗi riêng.

## 12. Lifecycle của một processor

Một processor thông thường được tạo instance và init **một lần cho một lượt tool processing**, không phải một instance mới mỗi round:

~~~text
Tìm tên/instance processor
       |
       v
constructor -> init(ProcessingEnvironment)
       |
       v
getSupportedAnnotationTypes(), getSupportedSourceVersion(), options
       |
       v
process(... round 1 ...)
       |
       v
process(... round tiếp theo nếu được dùng ...)
       |
       v
process(... final round nếu processor đã tham gia ...)
~~~

Do đó field như **generated** trong GeneratingProcessor có thể giữ trạng thái qua các rounds của **cùng invocation**. Nhưng không được dựa vào field này để chia sẻ trạng thái giữa hai lượt javac độc lập, dù build dùng daemon hoặc chạy song song.

Việc processor được discover không bảo đảm process được gọi; ở thực nghiệm Plain.java với FalseProcessor, processor không nhận vòng xử lý vì không có type phù hợp.

## 13. Chẩn đoán khi processor không chạy hoặc bị chặn

Một trình tự điều tra hiệu quả:

1. **Processor implementation đã biên dịch?** Kiểm tra processor-classes hoặc processor JAR có đúng package/class name.
2. **Annotation processing đã bật?** Có -proc:none không? Có chỉ định processor/processor path hoặc chế độ -proc phù hợp không?
3. **Service discovery đúng?** Tệp META-INF/services/javax.annotation.processing.Processor có tên đúng, implementation có constructor phù hợp không?
4. **Tên supported annotation type đúng?** demo.Flag khác Flag, demo.Use và module-qualified name khác.
5. **Annotation xuất hiện trong round nào?** Dùng -XprintRounds, đối chiếu root elements và generated sources.
6. **Processor trước claim annotation chưa?** Dùng -XprintProcessorInfo, kiểm tra return true/false.
7. **Processor có từng được kích hoạt chưa?** Nếu chưa match lần nào, final round không bắt buộc gọi nó.
8. **Phiên bản source phù hợp?** @SupportedSourceVersion và JDK/source level có thể tạo cảnh báo khi không tương thích.
9. **Có lỗi constructor/init/process?** Đọc compiler diagnostics thay vì chỉ xem stdout.
10. **IDE và terminal dùng cùng cấu hình?** So JDK, processorpath, proc mode, flags và output.
11. **Processor có sinh file đúng cách?** Theo dõi Filer, nguồn sinh và trường hợp tạo trùng.
12. **Có universal processor claim quá rộng?** Processor hỗ trợ "*" và return true có thể che các processor khác.

Ví dụ chẩn đoán:

~~~sh
javac -XprintRounds -XprintProcessorInfo --release 17 -processorpath processor-classes -processor processor.FalseProcessor,processor.TrueProcessor -d out1 src/demo/Flag.java src/demo/Use.java
~~~

Trong output, javac cho biết round nào chứa annotation types nào, processor nào **matches** và có return true/false. Log từ stdout/stderr và thứ tự trình bày chi tiết có thể khác giữa IDE, hệ điều hành hoặc các JDK; quan trọng là ý nghĩa các trường đó.

## 14. Quy tắc thiết kế processor phối hợp tốt

| Trường hợp | Cách lựa chọn claim thường hợp lý |
|---|---|
| Processor độc quyền xử lý annotation type riêng, là thành phần chính | Có thể return true nếu muốn claim type |
| Checker chỉ phát cảnh báo và muốn công cụ khác tiếp tục xử lý | Return false |
| Processor hỗ trợ "*" chỉ quét root elements | Thường return false để tránh claim mọi annotation |
| Nhiều processor cùng cần đọc type annotation | Thiết kế cơ chế phối hợp và tránh claim sớm không cần thiết |
| Processor codegen qua nhiều rounds | Giữ state theo invocation, claim theo type/round hợp lý |
| Processor phát lỗi | Dùng Messager ERROR; quyết định claim riêng |

Không dựa vào thứ tự phát hiện ngầm làm “hợp đồng” cho pipeline phức tạp. Nếu một processor cần output của processor khác, tổ chức rõ việc tạo source ở round trước và đọc generated source ở round sau, hoặc tách thành các task build có dependency được khai báo minh bạch.

## 15. An toàn của annotation processing

Annotation processors là **mã chạy trong build**. Một processor bên thứ ba có thể truy cập môi trường/files với quyền của tiến trình javac. Việc cấu hình processor path/danh sách processor tường minh giúp giảm nguy cơ vô tình chạy mã không mong muốn trên classpath.

Thực hành đáng tin:

- Chọn processor từ dependency/version có kiểm soát.
- Tách compile dependency, annotation processor dependency và runtime dependency.
- Không gửi bí mật môi trường vào source generated/log.
- Theo dõi nguồn được sinh và kiểm tra artifact build trước khi phát hành.
- Trên CI, dùng quyền hạn tối thiểu và kiểm tra JDK/toolchain đồng nhất.
- Khi nâng JDK, kiểm tra lại cách kích hoạt processors; đặc biệt chú ý thay đổi mặc định của javac từ JDK 23.

## 16. Câu hỏi luyện tập và đáp án định hướng

**Bài 1.** Có 20 class dùng @demo.Flag trong một round. Một processor hỗ trợ demo.Flag nhận bao nhiêu TypeElement trong tham số annotations? Trả lời: về mặt loại annotation, tập có demo.Flag; dùng roundEnv.getElementsAnnotatedWith để tìm những element cụ thể.

**Bài 2.** Vì sao FalseProcessor đứng trước TrueProcessor làm cả hai in [demo.Flag], còn đảo thứ tự chỉ TrueProcessor in? Trả lời: false giữ type unclaimed, true claim nó trong round.

**Bài 3.** Plain.java không dùng annotation. Vì sao StarProcessor được gọi nhưng FalseProcessor không? Trả lời: "*" có thể match tập rỗng ở round thông thường; demo.Flag thì không.

**Bài 4.** Vì sao GeneratingProcessor return true ở round 1 nhưng vẫn thấy demo.Flag ở round 2? Trả lời: source generated.Extra mang annotation type mới xuất hiện trong round mới, còn claim chỉ áp dụng từng round.

**Bài 5.** Processor phát hiện annotation sai nhưng trả true. Compiler có chắc sẽ fail không? Trả lời: không; phải phát chẩn đoán ERROR qua Messager hoặc gặp lỗi compiler thực sự.

**Bài 6.** Vì sao SOURCE retention vẫn được processor nhận? Trả lời: javac xử lý model nguồn lúc biên dịch, trước khi yêu cầu class file/runtme giữ annotation.

**Bài 7.** Dự án có processor JAR trên classpath nhưng javac 24 không tự chạy processor. Nên làm gì? Trả lời: cấu hình processing rõ ràng bằng -processor hoặc processor path/-proc:full theo tài liệu compiler, không dựa vào discovery ngầm.

**Bài 8.** Nếu universal validator không muốn chặn các processor khác, nên trả gì và vì sao? Trả lời: return false vì "*" có thể match rất nhiều loại annotation và return true sẽ claim tập được giao.

## 17. Những nhầm lẫn cần tránh

**“Đã có @Flag thì processor sẽ chạy.”** Sai. Cần discovery/kích hoạt và supported annotation types phù hợp.

**“Set annotations chứa danh sách mọi class dùng @Flag.”** Sai. Nó chứa **TypeElement cho các annotation types**. Muốn class/method/field cụ thể phải dùng RoundEnvironment.

**“@SupportedAnnotationTypes liệt kê các annotation đã gặp ở source.”** Sai. Nó là tuyên bố **khả năng hỗ trợ**, không phải kết quả từng round.

**“Return true = xử lý thành công; false = thất bại.”** Sai. Boolean thể hiện claim, không thể thay thế lỗi/chẩn đoán.

**“Claim annotation là xóa annotation khỏi class.”** Sai. Retention và class file metadata có quy tắc riêng.

**“Claim ở round 1 cấm mã sinh ra dùng annotation đó ở round 2.”** Sai. Quyết định claim được đánh giá theo round.

**“Nếu annotations rỗng thì chắc chắn là final round.”** Sai. Universal processor có thể nhận tập rỗng ở round thường.

**“Mọi processor được khai báo sẽ được gọi ở final round.”** Sai. Processor chưa từng được kích hoạt có thể không được gọi.

**“Dùng wildcard rồi luôn return true là cách an toàn nhất.”** Sai. Nó có thể vô tình claim mọi annotation type và cản processor khác.

## 18. Tài liệu tham khảo chính thức

- Oracle Java SE 24, **javax.annotation.processing.Processor**: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Oracle Java SE 24, **AbstractProcessor**: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html
- Oracle Java SE 24, **RoundEnvironment**: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html
- Oracle Java SE 24, **The javac Command**: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html
- Inside Java / OpenJDK, **JDK 23: Changes Default Annotation Processing Policy**: https://inside.java/2024/06/18/quality-heads-up/
- **JSR 269** — Pluggable Annotation Processing API, nền tảng của package javax.annotation.processing và javax.lang.model.

**Kết luận:** để biết processor xử lý annotation nào, hãy tách bạch **discovery → supported annotation types → annotation types hiện diện/chưa claim trong round → process → return true/false → vòng tiếp theo**. Claim là một hợp đồng phối hợp giữa processors ở thời điểm biên dịch, không phải thao tác thay đổi annotation trong mã nguồn, không phải bộ mã lỗi và không phải cơ chế điều khiển runtime.
