# javac: -processor, -processorpath và --processor-module-path

Java có cơ chế **annotation processing** ở thời điểm biên dịch. Một annotation processor triển khai interface §javax.annotation.processing.Processor§ (thường kế thừa §AbstractProcessor§), đọc các khai báo nguồn qua compiler model và có thể kiểm tra lỗi, phát diagnostics hoặc sinh source/resource. Để processor thực sự được chạy, cần phân biệt **chọn processor nào** và **nơi javac tìm processor đó**.

Ba tùy chọn chính:

- **§-processor§**: nêu **tên đầy đủ các lớp processor** muốn chạy, ví dụ §-processor tools.LogProcessor§. Đây là cơ chế **chọn tường minh**, bỏ qua quá trình auto-discovery mặc định.
- **§-processorpath§** hoặc dạng dài **§--processor-path§**: khai báo **đường dẫn chứa class/JAR của processor và dependency** khi chúng được nạp theo **classpath/unnamed module**.
- **§--processor-module-path§**: khai báo **module path dành riêng cho processor được đóng gói dưới dạng named modules**. Các processor module phải cung cấp service §javax.annotation.processing.Processor§ bằng khai báo §provides ... with ...§ thích hợp.

Chúng không phải ba cách viết khác nhau cho cùng một tùy chọn. Một lệnh có thể vừa cần chỉ định **processor cần chạy** vừa cần khai báo **vị trí tìm processor**, nhưng phải chọn cơ chế classpath hoặc JPMS phù hợp với cách processor được đóng gói.

## 1. Phân biệt application classpath và processor search path

Một lệnh biên dịch Java làm việc với **hai môi trường logic**:

1. **Compilation environment**: những source và dependency mà source của ứng dụng được phép tham chiếu, được cấu hình bằng §-classpath§/§--class-path§ hoặc §--module-path§ và các đường dẫn source thích hợp.
2. **Processor runtime environment**: những lớp processor và thư viện mà **javac phải nạp để chạy ngay trong lúc biên dịch**, được cấu hình bằng §-processorpath§ hoặc §--processor-module-path§.

Ví dụ:

~~~bash
javac --release 17 -cp libs/app-api.jar -processorpath tools/processor.jar -processor tools.LogProcessor -d out src/demo/Example.java
~~~

Đây là **lệnh minh họa** (phải có các đường dẫn/JAR tương ứng). Nó nói:

- §-cp libs/app-api.jar§: ứng dụng được biên dịch với API có trong §app-api.jar§.
- §-processorpath tools/processor.jar§: javac nạp implementation của processor từ §processor.jar§.
- §-processor tools.LogProcessor§: chạy processor có tên lớp §tools.LogProcessor§.
- §--release 17§: biên dịch source/API để nhắm Java 17.
- §-d out§: ghi class files của ứng dụng vào thư mục §out§.

**Không được suy rằng §-cp§ và §-processorpath§ là một đường dẫn duy nhất.** Chúng có chức năng khác nhau. Nếu **không khai báo processor path**, ở chế độ classpath, javac có thể tìm processors trong **user classpath** khi cơ chế discovery được kích hoạt. Nhưng nếu đã đặt §-processorpath§, đường dẫn này quyết định khu vực tìm processor classpath; thiếu dependency cần thiết của processor ở đây có thể gây §ClassNotFoundException§/§NoClassDefFoundError§ khi tải processor, ngay cả khi app compilation classpath có dependency trông tương tự.

### Bảng tra cứu nhanh

| Tùy chọn | Vai trò | Giá trị điển hình |
| --- | --- | --- |
| §-processor tools.P1,tools.P2§ | Chọn tên các processor chạy | Danh sách **binary class names**, phân cách dấu phẩy |
| §-processorpath path§ | Nơi tìm processor và dependencies theo classpath | Thư mục class hoặc JAR |
| §--processor-path path§ | Dạng dài của processor path | Như §-processorpath§ |
| §--processor-module-path path§ | Nơi tìm các **named processor modules** | Thư mục chứa module artifacts hoặc modular JAR |
| §-cp path§, §--class-path path§ | Classpath của mã **đang được biên dịch** | App API/dependency |
| §--module-path path§ | Module path của mã **đang được biên dịch** | JPMS dependencies của ứng dụng |
| §-proc:none§ | Tắt annotation processing | Không chạy processor |
| §-proc:only§ | Chỉ xử lý annotation, không biên dịch ra application class files | Kiểm tra/generate source |
| §-proc:full§ | Thực hiện annotation processing rồi biên dịch | Processing + compilation |
| §-Akey=value§ | Truyền option cho processor | §-Amode=explicit§ |
| §-s dir§ | Nơi lưu các source files do processor tạo | §-s generated§ |
| §-d dir§ | Nơi lưu class files do javac tạo | §-d classes§ |

**Dấu phân cách đường dẫn:** với processor path chứa nhiều thành phần, Windows dùng §;§ và Linux/macOS dùng §:§. Đường dẫn phải theo cách diễn giải của shell/HĐH. Ví dụ minh họa các lệnh trong bài dùng dấu §/§ cho tên file và một path duy nhất nên có thể áp dụng dễ dàng trên nhiều môi trường.

## 2. -processor: chọn tường minh processor theo tên lớp

Cú pháp:

~~~bash
javac -processor tools.LogProcessor -processorpath build/classpath-processor -d build/app src/demo/Example.java
~~~

Đây là **lệnh hoàn chỉnh khi đã chuẩn bị các file của ví dụ mục 5**. §-processor§ nhận một hoặc nhiều **tên lớp fully qualified** của processor, ngăn cách bằng dấu phẩy **không cần khoảng trắng**:

~~~bash
javac -processor tools.FirstProcessor,tools.SecondProcessor -processorpath build/processors -d build/app src/demo/Example.java
~~~

Lệnh thứ hai chỉ có tính **minh họa cú pháp**: phải thật sự tồn tại hai lớp processor đúng tên với constructor/provider hợp lệ.

Các điểm cần nhớ:

- §-processor§ là **class name**, không phải tên annotation (§@Generate§), không phải module name, không phải đường dẫn tới JAR.
- Nếu lớp processor không tồn tại trên processor search path hoặc không triển khai §Processor§ đúng cách, javac báo lỗi trước hoặc trong lúc xử lý.
- Dùng §-processor§ giúp build có tính lặp lại: danh sách processor được chọn rõ ràng, thay vì tình cờ nạp mọi provider được phát hiện.
- Một processor thường cần constructor không tham số có thể truy cập được và triển khai §javax.annotation.processing.Processor§ (trực tiếp hoặc thông qua §AbstractProcessor§).
- §-processor§ **bỏ qua cơ chế discovery mặc định**. Vì vậy trong ví dụ dùng §-processor§, **không cần** file §META-INF/services/...§.
- Processor chỉ định bởi §-processor§ vẫn làm việc theo processing rounds và lựa chọn các annotations dựa trên §getSupportedAnnotationTypes()§/§@SupportedAnnotationTypes§.

Phân biệt với §-Akey=value§: §-A§ không chọn processor, mà cung cấp một giá trị cấu hình qua §processingEnv.getOptions()§ **cho processor đã được chọn/nạp**.

## 3. -processorpath: tìm processor trên classpath

Tên ngắn §-processorpath§ và tên dài §--processor-path§ có cùng vai trò. Một đường dẫn có thể trỏ tới:

- Thư mục đã biên dịch chứa các §.class§ của processor.
- JAR chứa implementation của processor.
- Nhiều thư mục/JAR phân cách bằng path separator phù hợp với hệ điều hành.
- Dependencies cần thiết để **processor chạy** (không chỉ để source ứng dụng compile).

Nếu processor ở thư mục §build/classpath-processor§, lệnh:

~~~bash
javac --release 17 -processorpath build/classpath-processor -processor tools.LogProcessor -d build/app src/demo/Example.java
~~~

sẽ yêu cầu javac tải §tools.LogProcessor§ từ processor path. Trong mục 5, processor thật sự nằm trong package §tools§ nên class file có đường dẫn tương ứng như §build/classpath-processor/tools/LogProcessor.class§.

### Tự động phát hiện processor trên classpath

Nếu **không** dùng §-processor§, javac có thể phát hiện các processors trên processor path bằng Java service provider mechanism. Với classpath/JAR thường, cần resource:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file đó liệt kê provider classes, mỗi dòng một fully qualified class name:

~~~text
tools.LogProcessor
~~~

Khi §META-INF/services/javax.annotation.processing.Processor§ **được đóng gói bên trong processor JAR/thư mục trên processor path**, javac có thể discover provider đó nếu annotation processing đang được bật. File service có vị trí đặc biệt, **không phải Java source file** và **không phải annotation type**.

Hai cách làm phổ biến:

1. **Chọn tường minh:** §-processor tools.LogProcessor -processorpath ...§. Không yêu cầu service file.
2. **Discovery trên processor path:** cung cấp resource §META-INF/services/...§ và cấu hình §-processorpath ...§; javac tìm các processors được đăng ký.

Đối với build yêu cầu kiểm soát nguồn processor và bảo mật, nên dùng cấu hình tường minh hoặc danh sách dependency processor rõ ràng, không phụ thuộc việc một JAR bất ngờ chứa service provider.

### Lưu ý về JDK 23 trở lên

**Từ JDK 23**, javac **không còn ngầm chạy annotation processing chỉ vì tìm thấy processor trên classpath mà không có tùy chọn cấu hình processing**. Đây là thay đổi nhằm tránh tự động thực thi mã processor chỉ vì thêm một dependency.

Hãy **cấu hình tường minh** bằng §-processor§, §--processor-path§, §--processor-module-path§, hoặc bật §-proc:full§/§-proc:only§ khi phù hợp. Chỉ định §--processor-path§ với một service provider đúng là một cách yêu cầu processing. Với JDK 17/21/22, một số cấu hình cũ có thể mặc nhiên xử lý processor từ classpath; đừng dựa vào hành vi đó cho build cần làm việc trên nhiều JDK.

§-proc:full§ được giới thiệu ở JDK 21 và đã được backport tới nhiều bản cập nhật của các nhánh JDK cũ, gồm JDK 17u nhất định. Nếu môi trường dùng JDK 17 rất cũ không nhận §-proc:full§, hãy dùng cấu hình tường minh với §-processor§ và processor path, hoặc kiểm tra bản cập nhật JDK đang sử dụng.

## 4. --processor-module-path: tìm processor dưới dạng named JPMS module

Khi processor được đóng gói thành **named module**, dùng:

~~~bash
javac --processor-module-path build/modules -d build/app src/demo/Example.java
~~~

Khác §-processorpath§, §--processor-module-path§ yêu cầu artifacts theo **Java Platform Module System (JPMS)**. Processor ở một named module cần khai báo cung cấp service §javax.annotation.processing.Processor§.

Ví dụ §module-info.java§:

~~~java
module demo.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with tools.LogProcessor;
}
~~~

Ý nghĩa:

- §module demo.processor§: tên module của processor.
- §requires java.compiler§: cho phép module dùng §javax.annotation.processing§, §javax.lang.model§ từ module JDK §java.compiler§.
- §provides javax.annotation.processing.Processor with tools.LogProcessor§: đăng ký implementation §tools.LogProcessor§ cho ServiceLoader của môi trường javac.
- Không cần §exports tools§ chỉ để cung cấp processor service cho javac; §provides§ là cơ chế riêng cho provider.

**Tên module không phải tên lớp processor.** Trong ví dụ, module name là §demo.processor§, còn class name là §tools.LogProcessor§. Đừng truyền §-processor demo.processor§ chỉ vì đó là tên module; §-processor§ dùng tên lớp processor.

### Phân biệt --module-path và --processor-module-path

| Cấu hình | Phục vụ mục đích nào? |
| --- | --- |
| §--module-path app-modules§ | Modules mà **source ứng dụng** cần khi compile |
| §--processor-module-path processor-modules§ | Modules chứa **annotation processors** và dependencies để javac tải/chạy |

Hai loại modules có thể cùng tồn tại trong một build nhưng thuộc hai nhiệm vụ khác nhau. Ví dụ ứng dụng ở **unnamed module/classpath** vẫn có thể được xử lý bởi một processor đóng gói trong **named module**; ví dụ chạy được ở mục 6 chứng minh trường hợp này.

Khi processor module có dependencies, phải để các dependency modules tương ứng trên processor module path. §-cp§ của app không tự bổ sung chúng vào processor layer.

## 5. Ví dụ runnable A — classpath processor với -processor và -processorpath

Tạo cấu trúc thư mục:

~~~text
project/
├── src/
│   ├── processor/
│   │   ├── module-info.java
│   │   └── tools/
│   │       └── LogProcessor.java
│   └── app/
│       └── demo/
│           └── Example.java
└── build/
    ├── classpath-processor/
    ├── classpath-app/
    ├── modules/
    │   └── demo.processor/
    └── module-app/
~~~

Các thư mục §build/...§ là **thư mục output** được tạo trước khi chạy javac. Cụ thể, JDK javac không tự tạo mọi thư mục được truyền vào §-d§, nên hãy tạo trước §build/classpath-processor§, §build/classpath-app§, §build/modules/demo.processor§ và §build/module-app§. Trong phần này, chỉ cần §LogProcessor.java§ và §Example.java§; file §module-info.java§ dùng ở mục 6.

### File src/processor/tools/LogProcessor.java

~~~java
package tools;

import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
@SupportedOptions("mode")
public final class LogProcessor extends AbstractProcessor {
    private boolean printed;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (!printed && !round.processingOver()) {
            TypeElement sample = processingEnv.getElementUtils()
                    .getTypeElement("demo.Example");
            if (sample != null) {
                System.out.println("processor=" + sample.getQualifiedName());
                System.out.println("mode=" +
                    processingEnv.getOptions().getOrDefault("mode", "none"));
                printed = true;
            }
        }
        return false;
    }
}
~~~

Những điểm có ý nghĩa:

- §@SupportedAnnotationTypes("*")§ khai báo processor có thể nhận mọi annotation types; đây là thiết lập để demo dễ chạy trên source không có annotation riêng, không phải lựa chọn nên mặc định dùng cho mọi processor sản phẩm.
- §@SupportedSourceVersion(RELEASE_17)§ khai báo source version mà processor hỗ trợ.
- §@SupportedOptions("mode")§ khai báo processor chấp nhận option §mode§; giá trị nhận được qua §processingEnv.getOptions()§.
- §printed§ bảo đảm không log lặp ở nhiều processing rounds.
- §process§ trả §false§ để không claim toàn bộ annotations đối với những processors khác.
- §Elements.getTypeElement("demo.Example")§ chỉ cần model từ javac, không cần chạy lớp §Example§.

Với công cụ thật, nên dùng §Messager§ để báo diagnostics thay vì §System.out§, và cần xác định rõ phạm vi annotations xử lý.

### File src/app/demo/Example.java

~~~java
package demo;

public class Example {
    public static void main(String[] args) {
        System.out.println("app=ok");
    }
}
~~~

File §Example.java§ không có annotation tùy biến. Processor được kích hoạt thông qua tùy chọn compiler và §@SupportedAnnotationTypes("*")§.

### Bước 1: biên dịch processor classpath

Tại thư mục §project§, sau khi tạo các thư mục output:

~~~bash
javac --release 17 -encoding UTF-8 -d build/classpath-processor src/processor/tools/LogProcessor.java
~~~

Sau bước này, đường dẫn chứa bytecode của processor là §build/classpath-processor/tools/LogProcessor.class§.

### Bước 2: dùng processor trong lần biên dịch app

~~~bash
javac --release 17 -encoding UTF-8 -processorpath build/classpath-processor -processor tools.LogProcessor -Amode=explicit -d build/classpath-app src/app/demo/Example.java
~~~

**Stdout chính xác của lệnh javac thứ hai (đã thử trên JDK 24 với §--release 17§):**

~~~text
processor=demo.Example
mode=explicit
~~~

Lệnh này **chạy processor** và cũng compile §Example.java§ thành class file ở §build/classpath-app/demo/Example.class§.

Bây giờ chạy ứng dụng:

~~~bash
java -cp build/classpath-app demo.Example
~~~

**Stdout riêng của ứng dụng:**

~~~text
app=ok
~~~

Hai output khác nhau cho thấy một khác biệt nền tảng: **processor chạy trong JVM của javac tại compile time**, còn §main§ chạy sau trong JVM của ứng dụng. Processor không tự chạy lại mỗi lần ứng dụng khởi động.

## 6. Ví dụ runnable B — cùng processor được đóng gói trong named module

Giữ nguyên §LogProcessor.java§ và §Example.java§ như mục 5. Bổ sung file sau.

### File src/processor/module-info.java

~~~java
module demo.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with tools.LogProcessor;
}
~~~

Đây là source module declaration để javac xây **named processor module**. §provides ... with ...§ là cách ServiceLoader phát hiện implementation. Không cần tạo file §META-INF/services/javax.annotation.processing.Processor§ cho module này.

### Bước 1: biên dịch processor module

~~~bash
javac --release 17 -encoding UTF-8 -d build/modules/demo.processor src/processor/module-info.java src/processor/tools/LogProcessor.java
~~~

Cấu trúc output sau khi compile:

~~~text
build/
└── modules/
    └── demo.processor/
        ├── module-info.class
        └── tools/
            └── LogProcessor.class
~~~

Thư mục §build/modules§ là nơi javac tìm các modules; mỗi thư mục con như §demo.processor§ là một exploded module. Có thể thay exploded module bằng modular JAR đặt trên processor module path.

### Bước 2: dùng --processor-module-path

~~~bash
javac --release 17 -encoding UTF-8 --processor-module-path build/modules -Amode=module -d build/module-app src/app/demo/Example.java
~~~

**Stdout chính xác của lệnh biên dịch app (đã kiểm thử với JDK 24, §--release 17§):**

~~~text
processor=demo.Example
mode=module
~~~

Kết quả này xác nhận javac tìm processor từ named module với provider được khai báo bằng §module-info.class§. Ứng dụng §Example§ vẫn không cần §module-info.java§ riêng; ứng dụng được compile như classpath application trong ví dụ.

Nếu chỉ thay lệnh trên bằng:

~~~bash
javac --release 17 -encoding UTF-8 --module-path build/modules -d build/module-app src/app/demo/Example.java
~~~

thì bạn **không** cấu hình processor module path. §--module-path§ trên đây là **đường dẫn dependencies của ứng dụng**, không thay thế §--processor-module-path§. Đây là **đoạn so sánh cấu hình**, không phải lệnh kỳ vọng có stdout §processor=...§.

### Có cần thêm -processor khi đã có provides không?

Trong ví dụ này **không cần**, vì §--processor-module-path§ cùng khai báo service §provides§ đã đủ để processor được discovery. Nếu muốn chỉ định chính xác một hoặc nhiều processors cho build, có thể thêm tên processor phù hợp bằng §-processor§ theo hợp đồng của phiên bản javac đang dùng.

Tính chất “named processor module” thuộc về **đường dẫn và module descriptor của processor**, không phụ thuộc ứng dụng đang dùng classpath hay JPMS.

## 7. -proc:none, -proc:only và -proc:full

Ba chế độ rất hữu ích khi debug hoặc thiết lập build:

| Giá trị | Annotation processing | Biên dịch class files của ứng dụng |
| --- | --- | --- |
| §-proc:none§ | Không | Có, nếu source hợp lệ |
| §-proc:only§ | Có | Không chạy bước compile ra application class files |
| §-proc:full§ | Có | Có |

Dùng lại processor classpath ở mục 5:

### Chạy compile mà tắt processor

~~~bash
javac --release 17 -encoding UTF-8 -proc:none -processorpath build/classpath-processor -d build/no-process src/app/demo/Example.java
~~~

**Không có stdout §processor=...§**: chỉ compile app. Trong ví dụ, lệnh thành công và class file của ứng dụng có thể được tạo trong §build/no-process§. §-proc:none§ là cờ chủ động **vô hiệu hóa annotation processing**, dù processor có nằm trên processor path.

### Chỉ chạy processor, không tạo application class files

~~~bash
javac --release 17 -encoding UTF-8 -proc:only -processorpath build/classpath-processor -processor tools.LogProcessor -Amode=only -d build/proc-only src/app/demo/Example.java
~~~

**Stdout:**

~~~text
processor=demo.Example
mode=only
~~~

Ở chế độ này, javac không tạo §build/proc-only/demo/Example.class§. Tuy nhiên nếu processor được thiết kế để tạo **source/resource files**, công đoạn xử lý annotation vẫn có thể tạo những artifact đó tùy logic processor và các option §-s§/§-d§.

### Biên dịch và xử lý đầy đủ

§-proc:full§ yêu cầu vừa xử lý annotation vừa biên dịch. Hãy kiểm tra javac version trước khi dùng trên JDK 17 cũ vì giá trị §full§ đã được backport vào một số bản cập nhật. Trong demo với §-processor§ đã tường minh, không cần thêm §-proc:full§ để được processing+compilation khi sử dụng phiên bản javac hiện đại.

## 8. ServiceLoader: quy tắc đăng ký khác nhau giữa hai cơ chế

| Tiêu chí | Processor classpath | Named processor module |
| --- | --- | --- |
| Đường dẫn | §-processorpath§/§--processor-path§ | §--processor-module-path§ |
| Đăng ký tự động | §META-INF/services/javax.annotation.processing.Processor§ | §provides javax.annotation.processing.Processor with ...§ trong §module-info.java§ |
| Chọn processor trực tiếp | §-processor tools.LogProcessor§ | Có thể chỉ định processor class name phù hợp |
| Dependency location | Classpath dành cho processor | JPMS modules dành cho processor |
| Module descriptor bắt buộc? | Không | Có, để là explicit named module với provider declaration |
| App phải là named module? | Không | **Không**; demo module processor xử lý classpath app |
| Kết quả | Processor chạy trong compilation | Processor chạy trong compilation |

**Cảnh báo thường gặp:** chỉ có §@SupportedAnnotationTypes§ trên processor **không đủ để nó được auto-discovery**. §@SupportedAnnotationTypes§ quyết định loại annotations mà processor nhận **sau khi đã được nạp/khởi tạo**; ServiceLoader resource, §-processor§ hoặc named-module §provides§ mới giải quyết bài toán **tìm và nạp implementation**.

Trong cùng một source project, có thể build processor theo classpath hoặc named module; **đừng trộn metadata chưa tương ứng**. Khi copy JAR sang processor module path, kiểm tra nó có §module-info.class§ với §provides§ hoặc có cơ chế module/service registration phù hợp. Một JAR classpath có resource §META-INF/services§ không mặc nhiên trở thành explicit named module có module descriptor đúng.

## 9. Tùy chọn -A, -s, -d và -XprintRounds/-XprintProcessorInfo

Annotation processor thường nhận cấu hình qua §-Akey=value§:

~~~bash
javac --release 17 -processorpath build/classpath-processor -processor tools.LogProcessor -Amode=debug -d build/classpath-app src/app/demo/Example.java
~~~

Trong code, §processingEnv.getOptions().get("mode")§ trả §debug§. Để tránh compiler cảnh báo option không được nhận, processor nên khai báo §@SupportedOptions("mode")§ hoặc ghi đè §getSupportedOptions()§.

Một số tùy chọn bổ sung:

- **§-d dir§**: đặt class output. Tạo thư mục output trước; processor viết class/resource vào Filer output location liên quan có thể phụ thuộc cấu hình này.
- **§-s dir§**: đặt generated source output. Dùng khi processor tạo files §.java§; không phải đường dẫn tìm processor.
- **§-XprintRounds§**: hiển thị các rounds của annotation processing, đặc biệt hữu ích khi processor sinh source khiến có thêm rounds.
- **§-XprintProcessorInfo§**: hiển thị processor nào được gọi và annotations nó được yêu cầu xử lý; dùng để chẩn đoán processor không chạy hoặc không nhận đúng annotation types.

Ví dụ quan sát rõ những gì javac thực thi:

~~~bash
javac --release 17 -XprintRounds -XprintProcessorInfo -processorpath build/classpath-processor -processor tools.LogProcessor -Amode=inspect -d build/classpath-app src/app/demo/Example.java
~~~

**Không coi output debug flags là stdout cố định của bài**: nó có thể đổi theo JDK, annotations trong source và số processing rounds. Khi cần test tự động, assert vào kết quả chức năng §processor=...§, file được tạo hoặc compiler diagnostic thay vì dựa vào từng dòng log của javac.

## 10. Quy trình chẩn đoán khi processor không chạy

### Trường hợp 1: Có processor trong dependencies nhưng không có kết quả

Đầu tiên, kiểm tra có bật annotation processing **tường minh** không, nhất là với JDK 23+. Với processor classpath và muốn chọn chính xác, dùng §-processor tools.LogProcessor -processorpath ...§. Với named module, dùng §--processor-module-path ...§ và đảm bảo module khai báo §provides§.

### Trường hợp 2: javac báo processor not found

Ví dụ lỗi thường gặp:

~~~text
error: Annotation processor 'tools.LogProcessor' not found
~~~

Thông điệp chính xác tùy javac version. Kiểm tra:

- Tên lớp có đầy đủ package không, ví dụ §tools.LogProcessor§ chứ không phải §LogProcessor§.
- Class file/JAR có thực sự tồn tại dưới processor path/module path không.
- Processor và dependencies đã được **biên dịch trước** khi compile source app chưa.
- Class có triển khai §javax.annotation.processing.Processor§ và public/no-arg constructor phù hợp không.
- Nếu dùng module path, §module-info.class§ có §provides ... with ...§ không.

Không sửa bằng cách cho hết libraries vào app classpath một cách mù quáng: cần phân biệt compilation environment và processor runtime environment.

### Trường hợp 3: Có processor nhưng không xử lý annotation mong đợi

§-processor§ chỉ bảo đảm javac thử nạp/chạy processor; còn loại annotation xử lý do §getSupportedAnnotationTypes()§ quyết định. Nếu processor chỉ hỗ trợ §com.example.Check§ nhưng source dùng annotation khác, processor có thể không được gọi cho annotation mong đợi. Kiểm tra:

- Package/name của annotation cần match đúng.
- Source annotation có §@Target§ hợp lệ ở nơi sử dụng.
- Compiler đang compile đúng source và đường dẫn classes.
- §@SupportedSourceVersion§ có phù hợp language level không.
- Round behavior và processor nào claim annotation.
- §-XprintRounds§, §-XprintProcessorInfo§ để xem flow.

### Trường hợp 4: ClassNotFoundException hoặc NoClassDefFoundError khi processor chạy

Processor có thể phụ thuộc thư viện bên thứ ba **chỉ dùng khi processor đang chạy**. Nếu library ấy không nằm trên processor search path, nạp processor sẽ thất bại dù app dependencies đầy đủ. Đưa library đúng nơi:

- Classpath processor: bổ sung JAR vào §-processorpath§ theo separator HĐH.
- Named processor module: bổ sung dependency modules lên §--processor-module-path§ và khai báo §requires§ trong module descriptor theo đúng quan hệ JPMS.

Không được mặc định §--module-path§ của ứng dụng sẽ tự thỏa mọi processor runtime dependency.

### Trường hợp 5: Có hai processor cùng tạo một file

ServiceLoader có thể tìm nhiều processors từ các JAR khác nhau. Nếu cả hai tạo cùng tên source qua §Filer§, javac có thể báo lỗi tạo file trùng. Giới hạn danh sách processors bằng §-processor§, thu hẹp processor dependencies, hoặc điều chỉnh contract của processors.

### Trường hợp 6: Dùng -proc:only rồi không thấy .class của ứng dụng

Đây là hành vi **đúng** của §-proc:only§. Muốn compile app sau processing, bỏ §-proc:only§ hoặc chạy lượt compile khác. Dùng §-proc:full§ khi javac version có hỗ trợ hoặc lệnh với §-processor§ tường minh ở chế độ processing + compilation mặc định.

### Trường hợp 7: Dùng --module-path thay --processor-module-path

§--module-path§ cung cấp application modules, **không** đồng nghĩa tìm provider processor. Chọn §--processor-module-path§ cho named processor modules và kiểm tra §provides javax.annotation.processing.Processor with ...§.

## 11. Khi nào chọn mỗi chiến lược?

**Chiến lược A — Processor classpath với -processor tường minh**

Phù hợp cho một công cụ nội bộ, bài tập annotation processing, build nhỏ hoặc quá trình compile bạn cần biết chính xác processor nào chạy:

~~~bash
javac --release 17 -processorpath build/classpath-processor -processor tools.LogProcessor -d build/classpath-app src/app/demo/Example.java
~~~

Ưu điểm: dễ hiểu, không cần service metadata, dễ tái lập lỗi. Nhược điểm: phải cấu hình rõ tên processor và dependencies.

**Chiến lược B — Processor classpath dùng service auto-discovery**

Phù hợp khi phát hành một processor JAR đã đóng gói service provider resource và build quản lý rõ processor dependency. Không cần §-processor§ nhưng phải cấu hình processor path và bật processing tương ứng. Dùng §-XprintProcessorInfo§ để quan sát thứ gì được phát hiện.

**Chiến lược C — Named processor module**

Phù hợp với các công cụ build đã module hóa processor và dependencies theo JPMS. Dùng §--processor-module-path§ và §module-info.java§ có §provides§. Đây là tách biệt của processor runtime layer, không phải yêu cầu ứng dụng bắt buộc phải là named module.

Trong CI hoặc build nhạy cảm về security, các processor là **mã có thể được javac thực thi trong lúc build**. Chỉ cho phép các processor/JAR đáng tin, pin phiên bản dependencies, kiểm soát search paths, và đừng giả định “annotation processing chỉ đọc metadata nên không có code thực thi”.

## 12. Tự kiểm tra kiến thức

**1. §-processor§ khác §-processorpath§ thế nào?** §-processor§ chọn tên lớp implementation muốn chạy; §-processorpath§ nói javac tìm lớp và dependencies đó ở đâu khi dùng classpath-based processor.

**2. Khi thêm §my-processor.jar§ vào §-cp§ của app, processor có luôn chạy không?** Không thể mặc định như vậy. Discovery, service metadata, search path, phiên bản JDK và việc yêu cầu processing quyết định processor có được chạy. Từ JDK 23, cần cấu hình processing tường minh.

**3. Với named processor module, file nào khai báo service provider?** §module-info.java§, dùng §provides javax.annotation.processing.Processor with tools.LogProcessor;§ trong module descriptor.

**4. §--module-path§ có thay thế §--processor-module-path§ không?** Không. Cái trước phục vụ module dependencies của source ứng dụng; cái sau phục vụ annotation processors ở named modules.

**5. Dùng §-proc:only§ thì chương trình §Example§ có thể chạy ngay sau đó không?** Không nếu chưa có application class file từ bước compile khác, vì §-proc:only§ không thực hiện compile ra §Example.class§.

**6. Muốn truyền chuỗi §mode=debug§ cho processor phải dùng gì?** §-Amode=debug§; đọc qua §processingEnv.getOptions()§ và nên khai báo §@SupportedOptions("mode")§.

**7. Processor chạy ở runtime của ai?** Nó được javac nạp và thực thi **trong quá trình compilation**, khác JVM chạy §demo.Example.main§ sau đó.

**8. Nếu có §@SupportedAnnotationTypes("*")§ thì đã đủ cho ServiceLoader tự thấy processor chưa?** Chưa. Cần registration thông qua file §META-INF/services§ trên processor classpath, §provides§ ở named module, hoặc nêu rõ §-processor§.

## 13. Tài liệu chính thức

- **JDK 17 — javac Command**, gồm §-processor§, §-processorpath§, §--processor-module-path§, §-A§, §-proc§: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- **JDK 25 — javac Command**, thay đổi ở các phiên bản JDK mới: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- **JDK 23 Release Notes — Annotation Processing disabled by default without explicit configuration (JDK-8321314)**: https://www.oracle.com/java/technologies/javase/23-relnote-issues.html
- **Java SE 21 — javax.annotation.processing.Processor**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html
- **Java SE 21 — ProcessingEnvironment**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html
- **JPMS — module declarations (§7.7) và provides service**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7

**Kết luận:** hỏi lần lượt **“chạy processor nào?”** (§-processor§), **“tìm nó ở đâu?”** (§-processorpath§ nếu classpath, §--processor-module-path§ nếu named modules), và **“xử lý annotation ở chế độ nào?”** (§-proc:none/only/full§ hoặc cấu hình tường minh tương ứng). Khi ba câu trả lời rõ ràng, một build annotation processing sẽ ổn định hơn, dễ debug hơn và ít phụ thuộc vào cơ chế discovery ngầm của javac.