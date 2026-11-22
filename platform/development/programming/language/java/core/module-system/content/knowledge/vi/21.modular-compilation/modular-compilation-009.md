# Phân biệt compile classpath với processor path

## Mục tiêu

Sau bài này, bạn có thể phân biệt đường dẫn thư viện mà javac dùng để biên dịch mã nguồn với đường dẫn mà javac dùng để nạp annotation processor; cấu hình hai đường dẫn bằng tùy chọn phù hợp; và hiểu cách processor được phát hiện, chạy, tạo mã nguồn rồi tham gia quá trình biên dịch.

## 1. Hai đường dẫn phục vụ hai vai trò khác nhau

Khi biên dịch Java, javac có thể cần tìm hai nhóm thành phần:

1. **Compile classpath**: các class hoặc JAR mà mã nguồn đang biên dịch tham chiếu tới, chẳng hạn thư viện chứa kiểu dữ liệu, interface, annotation hoặc superclass.
2. **Processor path**: các class hoặc JAR chứa annotation processor mà chính trình biên dịch cần nạp và chạy trong quá trình xử lý annotation.

Hai nhóm này có thể đều là JAR, nhưng chúng không có cùng nhiệm vụ.

| Tiêu chí | Compile classpath | Processor path |
|---|---|---|
| Mục đích | Tìm kiểu và class cần thiết để kiểm tra, biên dịch mã nguồn | Tìm lớp annotation processor và dependency của processor |
| Javac option | -classpath, --class-path hoặc -cp | -processorpath hoặc --processor-path |
| Thành phần thường có | Thư viện API, model, annotation, thư viện bên thứ ba mà source sử dụng | JAR triển khai javax.annotation.processing.Processor và các thư viện mà processor cần |
| Được dùng để | Phân giải kiểu, kiểm tra chữ ký phương thức, kiểu tham số, kế thừa và tham chiếu trong source | Nạp processor, gọi các vòng xử lý annotation và tạo source/class/resource |
| Có thay thế đường dẫn kia không? | Không thay thế processor path | Không thay thế compile classpath |
| Có tự trở thành dependency runtime của ứng dụng không? | Không; runtime cần được cấu hình riêng | Không; processor thường chỉ cần trong lúc build |

Hãy nhớ: compile classpath giúp javac hiểu mã nguồn đang biên dịch; processor path giúp javac biết phải nạp công cụ xử lý annotation nào.

## 2. Compile classpath dùng để làm gì?

Giả sử ứng dụng sử dụng kiểu com.acme.model.Customer nằm trong JAR model-api.jar:

~~~java
package com.acme.app;

import com.acme.model.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("An");
        System.out.println(customer.name());
    }
}
~~~

Javac cần tìm Customer.class để kiểm tra constructor, kiểu trả về, phương thức và các quy tắc kiểu liên quan. Ta đặt JAR chứa kiểu đó trên compile classpath:

~~~bash
javac \
    -classpath lib/model-api.jar \
    -d build/classes \
    src/com/acme/app/Main.java
~~~

Các tùy chọn:

- -classpath (viết ngắn là -cp, hoặc tên đầy đủ --class-path) chỉ định nơi javac tìm class và JAR phục vụ việc biên dịch.
- -d chỉ định thư mục chứa class file đầu ra.
- File nguồn được đưa vào cuối lệnh.

Nếu có nhiều thư viện, phân tách các đường dẫn bằng ký tự phân tách path của hệ điều hành:

~~~bash
# Linux hoặc macOS: dấu hai chấm
javac -cp "lib/model-api.jar:lib/logging.jar" -d build/classes src/com/acme/app/Main.java
~~~

~~~powershell
# Windows: dấu chấm phẩy
javac -cp "lib\model-api.jar;lib\logging.jar" -d build\classes src\com\acme\app\Main.java
~~~

Compile classpath chỉ phục vụ lần gọi javac đó. Khi chạy ứng dụng, lệnh java có classpath riêng; các thư viện cần ở runtime phải được cung cấp cho tiến trình chạy. Việc một JAR xuất hiện trong javac -cp không tự động đóng gói JAR đó vào ứng dụng.

Nếu source được tổ chức thành named module, hãy cân nhắc --module-path để tìm module dependency. --class-path và --module-path phục vụ hai mô hình phân giải khác nhau; một JAR modular đặt trên classpath sẽ không được phân giải như named module theo JPMS.

## 3. Annotation processor là gì?

Annotation processor là một thành phần chạy trong quá trình biên dịch. Nó đọc annotation và thông tin cấu trúc chương trình do compiler cung cấp, sau đó có thể kiểm tra quy ước hoặc sinh thêm mã nguồn, class file và tài nguyên.

Ví dụ, một thư viện có annotation:

~~~java
package com.acme.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateBuilder {
}
~~~

Lập trình viên đánh dấu lớp cần sinh builder:

~~~java
package com.acme.app;

import com.acme.annotations.GenerateBuilder;

@GenerateBuilder
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
~~~

Một processor có thể phát hiện @GenerateBuilder, đọc các thành phần của lớp Customer rồi sinh thêm CustomerBuilder.java. Compiler sẽ đưa source được sinh vào các vòng xử lý tiếp theo và biên dịch nó cùng các source khác khi quá trình hoàn tất.

Annotation processor không phải là thư viện mà ứng dụng gọi như một phương thức khi chạy. Nó là mã thực thi được javac nạp trong môi trường build. Processor có thể tạo ra mã được ứng dụng sử dụng, nhưng bản thân JAR processor thường không cần có mặt ở runtime.

## 4. Processor path dùng để làm gì?

Javac cần biết vị trí của lớp triển khai javax.annotation.processing.Processor. Với processor nằm trong JAR riêng, ta dùng -processorpath:

~~~bash
javac \
    -classpath "lib/model-api.jar:lib/acme-annotations.jar" \
    -processorpath tools/acme-processor.jar \
    -processor com.acme.processor.CustomerProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

Ở đây:

- -classpath cung cấp các kiểu mà source sử dụng, gồm model API và annotation API.
- -processorpath chỉ nơi javac tìm implementation của processor.
- -processor chỉ định tên đầy đủ của processor cần chạy. Khi dùng tùy chọn này, không cần dựa vào việc tự phát hiện processor qua file service.
- -s chỉ định thư mục chứa source được sinh.
- -d chỉ định thư mục chứa class file.

Nếu processor phụ thuộc vào thư viện khác, các JAR đó cũng phải có trên processor path. Ví dụ:

~~~bash
javac \
    -classpath "lib/acme-annotations.jar:lib/model-api.jar" \
    -processorpath "tools/acme-processor.jar:tools/processor-utils.jar" \
    -processor com.acme.processor.CustomerProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

Trên Windows, thay dấu : trong danh sách đường dẫn bằng dấu ;. Đường dẫn processor chỉ phục vụ javac nạp công cụ và dependency của nó; nó không làm các thư viện trên processor path tự động trở thành compile dependency của ứng dụng.

## 5. Javac tìm processor như thế nào?

Có hai cách thường gặp để chọn processor:

**Chỉ định trực tiếp bằng -processor**

~~~bash
javac \
    -cp lib/acme-annotations.jar \
    -processorpath tools/acme-processor.jar \
    -processor com.acme.processor.CustomerProcessor \
    src/com/acme/app/Customer.java
~~~

Cách này nêu rõ processor class cần chạy. Nó hữu ích khi dự án có nhiều processor nhưng chỉ muốn kích hoạt một nhóm cụ thể.

**Tự phát hiện qua service provider configuration**

Với processor đóng gói trên classpath của processor, JAR có thể chứa file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file là tên đầy đủ của từng processor, mỗi tên trên một dòng:

~~~text
com.acme.processor.CustomerProcessor
~~~

Khi javac được cấu hình để thực hiện annotation processing và quét đường dẫn processor tương ứng, cơ chế service provider sẽ tìm các lớp được đăng ký trong file này.

Nếu JAR processor không có file service, có thể chỉ định tên processor bằng -processor. Ngược lại, nếu dùng discovery, cần bảo đảm file service nằm đúng đường dẫn và tên lớp trong đó chính xác.

## 6. Một processor đơn giản trông như thế nào?

Processor thường kế thừa AbstractProcessor:

~~~java
package com.acme.processor;

import com.acme.annotations.GenerateBuilder;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import java.util.Set;

@SupportedAnnotationTypes("com.acme.annotations.GenerateBuilder")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CustomerProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (var element :
                roundEnv.getElementsAnnotatedWith(GenerateBuilder.class)) {
            processingEnv.getMessager().printMessage(
                javax.tools.Diagnostic.Kind.NOTE,
                "Found @GenerateBuilder on " + element.getSimpleName(),
                element
            );

            // Có thể dùng processingEnv.getFiler()
            // để tạo source, class hoặc resource.
        }

        return true;
    }
}
~~~

Các thành phần đáng chú ý:

- @SupportedAnnotationTypes khai báo các annotation mà processor quan tâm.
- @SupportedSourceVersion khai báo phiên bản ngôn ngữ Java mà processor hỗ trợ.
- process(...) được gọi trong mỗi vòng xử lý annotation.
- RoundEnvironment cho biết các phần tử được đánh dấu trong vòng hiện tại.
- processingEnv.getMessager() gửi thông báo hoặc lỗi về compiler.
- processingEnv.getFiler() tạo source file, class file hoặc resource.

Một processor cần được biên dịch và đóng gói trước khi một lệnh javac khác có thể nạp nó qua processor path. Trong một dự án thực tế, thường có hai phần build: build JAR processor trước, sau đó dùng JAR đó khi biên dịch ứng dụng.

## 7. Annotation processing diễn ra theo các vòng

Annotation processing không chỉ là một lần gọi phương thức. Javac có thể chạy nhiều vòng:

1. Compiler phân tích source và tìm các annotation processor được cấu hình.
2. Processor nhận các annotation và phần tử chương trình liên quan trong vòng hiện tại.
3. Processor có thể tạo source hoặc resource mới qua Filer.
4. Source được tạo sẽ được đưa vào vòng tiếp theo để compiler và processor xử lý.
5. Khi không còn source mới cần xử lý, quá trình annotation processing kết thúc và compiler hoàn tất biên dịch.

Ví dụ: vòng đầu processor phát hiện @GenerateBuilder trên Customer và tạo CustomerBuilder.java. Ở vòng tiếp theo, javac có thể phân tích CustomerBuilder.java và các processor khác cũng có thể nhìn thấy mã nguồn mới.

Processor nên tránh tạo đi tạo lại cùng một file ở nhiều vòng. Filer sẽ báo lỗi nếu một file đã được tạo lại trong cùng một lần biên dịch. Nên kiểm tra annotation và trạng thái vòng để chỉ tạo nội dung cần thiết.

## 8. Phân biệt các tùy chọn javac liên quan

| Tùy chọn | Vai trò |
|---|---|
| -classpath, -cp, --class-path | Tìm class/JAR mà source cần để biên dịch |
| -processorpath, --processor-path | Tìm annotation processor và dependency của processor |
| --processor-module-path | Tìm annotation processor được đóng gói dưới dạng named module |
| -processor | Chọn rõ tên các processor cần chạy |
| -proc:none | Tắt annotation processing |
| -proc:only | Chạy annotation processing mà không biên dịch các source thành class |
| -proc:full | Thực hiện annotation processing và biên dịch |
| -s | Chọn thư mục chứa source được processor sinh |
| -d | Chọn thư mục chứa class file đầu ra |
| -Akey=value | Truyền tùy chọn riêng cho processor |

Lưu ý về phiên bản JDK: từ JDK 23, không nên dựa vào việc javac tự động dò và chạy processor chỉ vì JAR processor có mặt trên classpath. Hãy cấu hình tường minh processor bằng -processor, -processorpath, --processor-module-path, hoặc yêu cầu chế độ xử lý phù hợp bằng -proc:full hay -proc:only. Điều này giúp build rõ ràng và tránh việc vô tình thực thi processor không được dự định.

## 9. Processor dạng named module

Trong dự án dùng JPMS, annotation processor cũng có thể được đóng gói thành explicit module. Khi đó module descriptor đăng ký service provider:

~~~java
module com.acme.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with com.acme.processor.CustomerProcessor;
}
~~~

java.compiler chứa API annotation processing như Processor, AbstractProcessor, RoundEnvironment và ProcessingEnvironment.

Khi biên dịch ứng dụng, dùng processor module path:

~~~bash
javac \
    --class-path lib/acme-annotations.jar \
    --processor-module-path tools/com.acme.processor.jar \
    -s build/generated-sources \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

Khác biệt chính:

- --processor-path thường dùng cho processor được tìm như các class/JAR trên classpath.
- --processor-module-path dùng cho processor được tổ chức thành named module và có khai báo service trong module descriptor.
- --module-path là nơi tìm các module dependency mà source đang biên dịch cần đọc; không nên nhầm nó với processor module path.

Trong một build modular, có thể cần đồng thời module path cho dependency của source và processor module path cho processor. Mỗi đường dẫn phục vụ một vai trò riêng.

## 10. Ví dụ so sánh hai cấu hình

Giả sử có ba JAR:

~~~text
lib/
  customer-api.jar
  customer-annotations.jar
tools/
  customer-processor.jar
~~~

Source ứng dụng sử dụng Customer từ customer-api.jar và annotation từ customer-annotations.jar. Processor implementation nằm trong customer-processor.jar.

Cấu hình tách biệt:

~~~bash
javac \
    --class-path "lib/customer-api.jar:lib/customer-annotations.jar" \
    --processor-path tools/customer-processor.jar \
    -processor com.acme.processor.CustomerProcessor \
    -s build/generated \
    -d build/classes \
    src/com/acme/app/Customer.java
~~~

Trong lệnh này:

- Nếu bỏ customer-api.jar khỏi compile classpath, javac có thể báo không tìm thấy kiểu Customer hoặc các kiểu mà source tham chiếu.
- Nếu bỏ customer-processor.jar khỏi processor path và không có processor ở một đường dẫn được cấu hình khác, javac không thể nạp CustomerProcessor.
- Nếu bỏ customer-annotations.jar khỏi compile classpath, source không thể tham chiếu @GenerateBuilder.
- Đưa customer-processor.jar vào compile classpath không phải cách cấu hình rõ ràng để bảo đảm processor chạy; hãy dùng processor path hoặc chọn processor trực tiếp.

Tách đường dẫn cũng giúp dễ xem xét dependency nào chỉ dành cho build và dependency nào thực sự cần để biên dịch ứng dụng.

## 11. Cấu hình trong Maven và Gradle

Các build tool thường cung cấp cấu hình riêng cho annotation processor để không phải tự viết toàn bộ lệnh javac.

**Maven**

Trong maven-compiler-plugin, có thể khai báo processor dependency bằng annotationProcessorPaths:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>com.acme</groupId>
                <artifactId>customer-processor</artifactId>
                <version>1.0.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Các thư viện mà source ứng dụng cần vẫn được khai báo trong dependencies theo scope phù hợp. annotationProcessorPaths mô tả nơi plugin compiler tìm processor; nó không thay thế dependency của source.

**Gradle**

Với Java plugin, có thể tách annotation API và processor:

~~~groovy
dependencies {
    compileOnly("com.acme:customer-annotations:1.0.0")
    annotationProcessor("com.acme:customer-processor:1.0.0")
}
~~~

compileOnly làm annotation có sẵn khi biên dịch nhưng không tự thêm vào runtime classpath. annotationProcessor đưa processor vào cấu hình processor path của tác vụ biên dịch.

Tùy thư viện, annotation API có thể cần ở runtime hoặc được đóng gói cùng ứng dụng; hãy chọn scope theo retention và cách ứng dụng sử dụng annotation. Processor implementation thường chỉ cần trong build.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| package ... does not exist hoặc cannot find symbol ở source | Thiếu thư viện trên compile classpath hoặc module path | Thêm đúng dependency vào classpath/module path của source |
| Processor không chạy | Processor không có trên processor path, chưa được chọn, thiếu service registration hoặc annotation processing bị tắt | Kiểm tra -processorpath, -processor, file service và -proc |
| Annotation processor ... not found | Tên processor sai hoặc JAR không nằm trên processor path | Kiểm tra tên đầy đủ của lớp và vị trí JAR |
| NoClassDefFoundError khi nạp processor | Thiếu dependency mà chính processor cần | Thêm dependency đó vào processor path hoặc processor module path |
| Annotation không được nhận diện | Thiếu JAR annotation trên compile classpath/module path hoặc dùng sai tên annotation | Kiểm tra import và dependency của source |
| Generated source không xuất hiện ở nơi mong đợi | Chưa cấu hình -s hoặc build tool dùng thư mục generated khác | Kiểm tra thư mục đầu ra source của javac/build tool |
| Processor tạo file trùng | Nhiều vòng hoặc nhiều processor cùng tạo một tên file | Đảm bảo mỗi file chỉ được tạo một lần và tên file không xung đột |
| Build chạy processor trên JDK mới nhưng trước đây không chạy | Hành vi kích hoạt annotation processing thay đổi theo phiên bản JDK | Cấu hình processor tường minh và kiểm tra tùy chọn -proc |

Khi chẩn đoán, hãy xác định lỗi thuộc nhóm nào trước: source không tìm thấy kiểu, hay compiler không tìm thấy processor. Lỗi thứ nhất thường liên quan compile classpath/module path; lỗi thứ hai liên quan processor path, service registration hoặc chế độ annotation processing.

## Ghi nhớ

Compile classpath (-cp/--class-path) cung cấp các kiểu mà source cần để biên dịch. Processor path (-processorpath/--processor-path) cung cấp implementation và dependency của annotation processor để javac nạp trong lúc build. Với processor dạng named module, dùng --processor-module-path. Processor có thể kiểm tra annotation và sinh source qua Filer; source sinh ra được đưa vào các vòng xử lý tiếp theo. Hãy tách dependency của ứng dụng và công cụ build thành các đường dẫn riêng để build dễ kiểm soát, dễ tái lập và không vô tình thực thi processor ngoài dự định.