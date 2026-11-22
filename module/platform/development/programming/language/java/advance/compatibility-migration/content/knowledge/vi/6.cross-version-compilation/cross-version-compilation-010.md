# Kiểm tra mã sinh và bộ xử lý annotation theo phiên bản Java

Trong dự án Java, một phần mã được đưa vào ứng dụng không nhất thiết do lập trình viên viết trực tiếp. Mã có thể được tạo từ annotation, schema, file mô tả API, protobuf, WSDL hoặc công cụ build. Một số công cụ tạo file source trước khi biên dịch; một số annotation processor chạy bên trong compiler và tạo thêm Java source trong các vòng xử lý annotation. Khi nâng JDK hoặc thay đổi phiên bản Java mục tiêu, cả mã được sinh lẫn công cụ sinh mã đều cần được kiểm tra.

Một dự án có thể biên dịch thành công trên JDK cũ nhưng thất bại trên JDK mới vì annotation processor chưa hỗ trợ compiler mới, phụ thuộc vào API nội bộ của `javac`, không còn được tự động phát hiện hoặc sinh ra source/API không phù hợp với release mục tiêu. Ngược lại, processor có thể chạy thành công nhưng mã sinh ra lại không tương thích với runtime thấp nhất mà ứng dụng cần hỗ trợ.

Mục tiêu của bước kiểm tra là xác định mã nào được sinh, công cụ nào tạo ra nó, compiler/JDK nào chạy công cụ, source/API baseline nào áp dụng cho output và những phiên bản nào cần được kiểm thử.

## 1. Phân biệt các loại mã sinh trong dự án Java

Không phải mọi file được tạo tự động đều đến từ annotation processing. Cần phân loại đúng vì thời điểm chạy, cách cấu hình và cơ chế tương thích khác nhau.

### 1.1. Mã được tạo trước bước biên dịch

Một số công cụ đọc schema hoặc mô tả dịch vụ rồi tạo `.java` source trước khi `javac` chạy. Ví dụ:

- OpenAPI Generator tạo model, API interface và client/server stub từ OpenAPI document.
- Protocol Buffers compiler (`protoc`) cùng plugin Java tạo class từ file `.proto`.
- Công cụ sinh SOAP client tạo Java stub từ WSDL/XSD.
- Công cụ sinh mã từ database schema, DSL hoặc file cấu hình.
- Plugin build tạo source, resource hoặc metadata từ template.

Những công cụ này thường chạy như task riêng của Gradle/Maven. Cần kiểm tra phiên bản generator, plugin, schema đầu vào, runtime library đi kèm và JDK dùng để chạy chính công cụ đó. Sau khi được tạo, source vẫn phải biên dịch theo source/API baseline của ứng dụng.

### 1.2. Mã được tạo bởi annotation processor

Annotation processing là cơ chế chuẩn của Java compiler, được đặc tả qua JSR 269. Processor đọc annotation và thông tin kiểu trong compilation, sau đó có thể tạo source file, class file hoặc resource thông qua `Filer`.

Một số ví dụ phổ biến:

- MapStruct tạo implementation cho mapper interface.
- Dagger tạo mã phục vụ dependency injection.
- AutoValue và Immutables tạo implementation cho kiểu dữ liệu bất biến.
- QueryDSL có thể tạo metamodel hoặc query type từ entity.
- Hibernate/JPA metamodel processor tạo static metamodel.
- Một số processor tạo metadata, registry hoặc adapter dựa trên annotation riêng.

Lombok cũng tham gia quá trình biên dịch để bổ sung thành viên vào mô hình cú pháp của compiler. Cách hoạt động của Lombok có những chi tiết phụ thuộc vào implementation của `javac`, vì vậy cần đặc biệt kiểm tra ma trận hỗ trợ JDK của đúng phiên bản Lombok.

### 1.3. Phân biệt processor với annotation runtime

Annotation có thể chỉ phục vụ runtime reflection mà không tạo mã. Ví dụ, framework đọc annotation để cấu hình bean hoặc route khi ứng dụng khởi động. Trong trường hợp đó, cần kiểm tra runtime library và cách framework xử lý annotation trên JDK mới, nhưng không nhất thiết có annotation processor.

Ngược lại, một thư viện có thể vừa cung cấp annotation ở compile time vừa cung cấp runtime API. Ví dụ, processor tạo implementation còn ứng dụng cần runtime dependency để gọi implementation đó. Cần tách rõ các thành phần:

- Annotation/API được source code tham chiếu.
- Processor chạy trong compiler.
- Runtime library được ứng dụng sử dụng khi chạy.
- Generated source/class/resource được đưa vào artifact cuối.

Không nên đưa processor vào runtime classpath chỉ vì ứng dụng dùng annotation của nó. Hãy dùng đúng cấu hình compile-time và runtime theo hướng dẫn của thư viện.

## 2. Hiểu vòng đời annotation processing

`javac` thực hiện annotation processing trong các vòng (rounds). Processor được gọi với tập annotation và element có liên quan trong vòng hiện tại. Processor có thể tạo source mới; các source đó được đưa vào những vòng tiếp theo để compiler và processor xử lý. Quá trình kết thúc khi không còn source mới cần xử lý hoặc không còn vòng tiếp theo.

Một processor thường triển khai `javax.annotation.processing.Processor`, hoặc kế thừa `AbstractProcessor`. Nó khai báo annotation hỗ trợ, source version và tùy chọn cấu hình. Ví dụ cấu trúc đơn giản:

~~~java
@SupportedAnnotationTypes("com.example.GenerateMapper")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class MapperProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Đọc element có annotation và tạo source qua Filer.
        return false;
    }
}
~~~

Đây là ví dụ minh họa cấu trúc processor; phần tạo source và xử lý lỗi được lược bỏ. Trong implementation thực tế, processor cần xử lý nhiều annotation, nhiều round, kiểu generic, nested type, lỗi trùng tên và trường hợp compilation không có element phù hợp.

### 2.1. Processor được phát hiện như thế nào?

Một processor có thể được chỉ định trực tiếp bằng `-processor`, được phát hiện qua service provider metadata hoặc được đặt trên processor module path. Cơ chế service discovery truyền thống dùng file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

File này liệt kê tên đầy đủ của các processor implementation. Với modular JAR, processor cũng có thể khai báo service provider trong `module-info.java` và được phát hiện qua module path tương ứng.

Việc processor nằm trên compile classpath không đồng nghĩa nó luôn được chạy trong mọi phiên bản compiler. Cần xác định rõ processor được khai báo ở đâu, compiler được yêu cầu chạy nó bằng cách nào và build tool thực sự truyền option nào cho `javac`.

### 2.2. Các vòng xử lý và tạo file

Processor thường dùng `Filer` để tạo source hoặc resource. Tên file phải ổn định và không được tạo trùng trong cùng compilation. Nếu một processor cố ghi lại file đã được tạo, compiler có thể báo `FilerException`.

Các nguyên tắc quan trọng:

- Chỉ tạo file khi có element hợp lệ và có dữ liệu cần sinh.
- Tạo tên package/class ổn định, tránh phụ thuộc thứ tự duyệt element.
- Không ghi file vào source tree do người dùng quản lý nếu build tool đã cung cấp generated-source directory.
- Ghi chú hoặc metadata phù hợp để người đọc nhận biết file là generated output.
- Xử lý nhiều round và trạng thái `processingOver()` đúng cách.
- Báo lỗi qua `Messager` với vị trí element để developer biết annotation nào không hợp lệ.
- Tránh tạo cùng một type ở nhiều processor hoặc nhiều module.

Một lỗi thường gặp là processor chỉ chạy đúng khi clean build nhưng lỗi khi incremental build, hoặc ngược lại. Cần kiểm tra cả hai chế độ vì build tool có thể chỉ chạy lại processor khi những input mà nó theo dõi thay đổi.

## 3. Phân biệt JDK chạy processor với Java release của mã được biên dịch

Đây là điểm quan trọng nhất khi kiểm tra mã sinh theo phiên bản Java. Có ít nhất ba phiên bản cần phân biệt:

1. **JDK chạy build/compiler:** JVM thực thi Gradle/Maven và tiến trình `javac`.
2. **Source/API release mục tiêu:** phiên bản ngôn ngữ và Java SE API mà mã ứng dụng được phép sử dụng.
3. **Runtime tối thiểu:** phiên bản Java thấp nhất mà artifact cuối cần chạy.

Ví dụ, build có thể chạy bằng JDK 21, biên dịch ứng dụng với `--release 17`, rồi triển khai artifact trên JRE/JDK 17. Annotation processor chạy bên trong tiến trình compiler trên JDK 21. Tuy nhiên, source do processor tạo ra vẫn phải được biên dịch theo release 17.

`--release 17` giới hạn source language, bytecode và Java platform API mà compilation target được phép tham chiếu. Nó không biến JVM chạy processor thành JDK 17, cũng không ngăn processor tự gọi API của JDK 21 trong quá trình thực thi. Vì vậy, processor có thể hoạt động trên JDK 21 nhưng chưa chắc chạy được trên JDK 17 nếu chuyển build toolchain xuống JDK 17.

Ngược lại, processor chạy trên JDK 21 có thể sinh code gọi một API chỉ có từ JDK 21. Nếu output được biên dịch với `--release 17`, compiler thường phát hiện tham chiếu API đó và báo lỗi. Nhưng nếu processor tạo resource hoặc mã được biên dịch ở một task khác không dùng cùng release constraint, cần kiểm tra thêm để tránh lọt API mới vào artifact.

Hãy ghi ma trận rõ ràng thay vì dùng một cụm “Java version” chung:

| Thành phần | Ví dụ | Câu hỏi |
|---|---|---|
| JDK chạy Gradle/Maven | JDK 21 | Build tool và plugin có chạy trên JDK này không? |
| JDK chạy `javac` | Toolchain JDK 21 | Compiler và processor có hỗ trợ JDK này không? |
| Source/API release | `--release 17` | Source và API nào được phép dùng? |
| Bytecode target | Java 17 class file | Runtime nào có thể đọc bytecode? |
| Runtime tối thiểu | JDK 17 | Ứng dụng và generated code có chạy trên runtime này không? |
| Processor version | MapStruct/Lombok/... version cụ thể | Processor có hỗ trợ compiler và source model này không? |

Nếu build tool chạy bằng một JDK nhưng dùng toolchain khác để biên dịch, cần xác nhận chính xác process nào chạy processor. Thông thường processor được nạp và thực thi trong compiler process, vì vậy toolchain của task compile là thông tin quyết định.

## 4. Kiểm tra khả năng tương thích của annotation processor với JDK mới

Processor là một dependency chạy trong môi trường build. Nó có thể phụ thuộc vào Java compiler API, API của JDK, thư viện bytecode, reflection hoặc implementation nội bộ của `javac`.

### 4.1. Kiểm tra ma trận hỗ trợ của nhà cung cấp

Với từng processor, hãy tìm tài liệu hỗ trợ chính thức và release notes của đúng phiên bản. Xác minh:

- JDK tối thiểu để chạy processor.
- Các JDK đã được nhà cung cấp kiểm thử hoặc hỗ trợ chính thức.
- Source version tối đa mà processor hiểu đúng.
- Phiên bản Gradle/Maven và compiler plugin được hỗ trợ.
- Phiên bản framework, annotation API và runtime library cần đi kèm.
- Những thay đổi đã sửa liên quan tới JDK mới, module system hoặc incremental compilation.
- Các giới hạn đã biết và workaround được nhà cung cấp công bố.

Không suy ra hỗ trợ chỉ từ số version mới hơn hoặc việc dependency có thể tải về. Nếu tài liệu không nêu rõ JDK đích, hãy đánh dấu “chưa xác minh” và kiểm tra bằng build thử cùng bộ test đại diện.

### 4.2. Kiểm tra việc sử dụng API nội bộ của compiler

Java annotation processing API công khai gồm các package như `javax.annotation.processing`, `javax.lang.model.*` và các API compiler được đặc tả. Một số processor, đặc biệt các công cụ can thiệp sâu vào AST hoặc compiler internals, có thể sử dụng implementation class trong `com.sun.tools.javac.*`.

Các package nội bộ không phải hợp đồng ổn định của Java SE. JDK mới có thể thay đổi cấu trúc class, method hoặc quyền truy cập module. Processor cũ có thể gặp lỗi như:

- `IllegalAccessError` hoặc `InaccessibleObjectException` khi truy cập thành phần bị encapsulate.
- `NoSuchFieldError` hoặc `NoSuchMethodError` khi compiler internals thay đổi.
- `ClassCastException` hoặc lỗi xử lý tree/element do giả định về cấu trúc AST không còn đúng.
- Lỗi khởi tạo processor hoặc lỗi reflection xuất hiện trước khi compilation hoàn tất.

Khi gặp lỗi, hãy lấy stack trace đầy đủ để xác định lỗi nằm ở processor, compiler plugin hay source code. Tìm bản cập nhật chính thức của processor trước khi thêm `--add-exports` hoặc `--add-opens`. Nếu phải mở package nội bộ để duy trì tạm thời, giới hạn đúng package/module, ghi rõ lý do và thời hạn loại bỏ. Không dùng một tập JVM option mở rộng toàn bộ compiler internals như giải pháp mặc định.

### 4.3. Kiểm tra SourceVersion và cú pháp mới

Processor có thể khai báo source version mà nó hỗ trợ bằng `@SupportedSourceVersion` hoặc `getSupportedSourceVersion()`. Cần xem khai báo đó có phù hợp với source release đang biên dịch không.

Việc processor trả về `SourceVersion.latestSupported()` không tự chứng minh nó hiểu đúng mọi cú pháp mới. Nếu processor tự phân tích source, dùng `Tree API`, xử lý annotation trên record, sealed type, pattern hoặc construct mới, cần xác nhận implementation đã được cập nhật để hiểu các cấu trúc đó.

Với processor chỉ đọc `Element` và `TypeMirror` qua API chuẩn, rủi ro có thể thấp hơn, nhưng vẫn phải kiểm tra cách nó xử lý các loại element và type mới. Đặc biệt chú ý:

- Record component, record constructor và accessor.
- Sealed class/interface và permitted subclasses.
- Generic type, intersection type, annotation trên type use.
- Module element, package element và service provider.
- Annotation lặp lại, annotation trên parameter/type use và annotation kế thừa.
- Kiểu mới hoặc thay đổi biểu diễn trong `javax.lang.model` và `com.sun.source`.

Không phải mọi JDK mới đều bổ sung thay đổi ở tất cả các nhóm trên. Hãy đối chiếu đúng ngôn ngữ/source release và API compiler của phiên bản mục tiêu.

### 4.4. Kiểm tra discovery và cấu hình processor

JDK 23 thay đổi chính sách mặc định của `javac`: annotation processing không còn tự động chạy chỉ vì processor tình cờ được tìm thấy trên compile classpath. Việc chạy processor cần được yêu cầu rõ ràng, ví dụ qua `-processor`, `--processor-path`, `--processor-module-path` hoặc các chế độ `-proc:only`/`-proc:full` phù hợp.

Thay đổi này có thể làm một build cũ đột nhiên không tạo generated source sau khi chuyển JDK 23+, dù processor JAR vẫn có mặt trong dependency. Vì vậy cần kiểm tra build tool có cấu hình processor path hoặc processor selection tường minh hay không.

Trong `javac`, các option thường gặp gồm:

~~~bash
javac \
  --release 17 \
  --processor-path path/to/processor.jar \
  -processor com.example.MapperProcessor \
  -s build/generated/sources/annotations \
  -d build/classes \
  @sources.txt
~~~

- `--processor-path` chỉ định nơi tìm processor.
- `-processor` chỉ định processor class cần chạy.
- `-s` chỉ định thư mục output cho generated source.
- `-d` chỉ định thư mục output cho class file.
- `--release` chọn baseline source/API/bytecode cho mã được biên dịch.

Các option cụ thể có thể khác theo phiên bản compiler; kiểm tra `javac --help` của JDK đang dùng trước khi đưa vào build. `-proc:none` tắt annotation processing; `-proc:only` chỉ chạy processing mà không biên dịch các source như compilation thông thường; `-proc:full` cho phép cả processing và compilation. Không thêm `-proc:full` một cách máy móc nếu build tool đã cấu hình processor path và chính sách processing phù hợp.

Với Gradle, nên khai báo processor trong configuration chuyên biệt thay vì đặt lẫn trong `implementation`:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:<version>'
    annotationProcessor 'org.projectlombok:lombok:<version>'

    testCompileOnly 'org.projectlombok:lombok:<version>'
    testAnnotationProcessor 'org.projectlombok:lombok:<version>'
}
~~~

Ví dụ trên minh họa cấu hình Lombok; thay bằng phiên bản được hỗ trợ trong dự án. Các processor khác có thể cần runtime dependency riêng và cấu hình khác. Với Maven, dùng `annotationProcessorPaths` hoặc `annotationProcessors` của compiler plugin khi phù hợp, đồng thời kiểm tra cách plugin truyền option cho JDK đích.

## 5. Kiểm tra mã được sinh ra

Processor chạy thành công chưa đủ để kết luận output tương thích. Cần kiểm tra source/class/resource được sinh và artifact cuối cùng.

### 5.1. Source level và API được sinh

Generated source phải tuân theo source release mục tiêu. Nếu ứng dụng cần chạy trên Java 17, processor không được sinh cú pháp chỉ có ở Java 21 hoặc tham chiếu API chỉ xuất hiện từ Java 21.

Kiểm tra:

- Cú pháp source mà generator tạo ra.
- API Java SE được tham chiếu.
- Annotation và runtime dependency được generated code sử dụng.
- Generic signature, checked exception, visibility và package.
- Reflection metadata, service registration và module descriptor nếu có.
- Warning hoặc lỗi mới từ compiler đích.

Biên dịch generated source bằng `--release` là cách quan trọng để phát hiện cú pháp/API vượt quá baseline. Tuy nhiên, không phải mọi generator đều tạo source trong cùng compilation. Nếu codegen chạy thành task riêng, phải đảm bảo compile task của output cũng dùng đúng toolchain và release.

### 5.2. Kiểm tra runtime dependency

Generated class có thể tham chiếu tới runtime library của processor. Ví dụ, mapper được sinh có thể gọi helper runtime; Protobuf generated class phụ thuộc protobuf runtime; client được sinh từ OpenAPI có thể cần HTTP client và JSON library.

Hãy xác định:

- Dependency nào chỉ cần ở compile time để chạy processor.
- Dependency nào phải có trong runtime classpath.
- Phiên bản runtime library nào tương thích với generated code.
- Có xung đột phiên bản với dependency khác trong ứng dụng không.
- Generated code có dùng API chỉ tồn tại ở phiên bản runtime mới hơn không.

Không mặc định processor và runtime library luôn phải dùng cùng một version number, nhưng phải tuân thủ ma trận tương thích mà nhà cung cấp công bố.

### 5.3. Kiểm tra tính ổn định và khả năng tái tạo

Generated output nên ổn định khi input và tool version không đổi. Nếu kết quả phụ thuộc vào thứ tự duyệt file, timestamp, locale, timezone hoặc thứ tự collection không xác định, build có thể tạo diff không cần thiết và khó xác minh thay đổi thật.

Nên kiểm tra:

- Hai lần clean build với cùng input có tạo output tương đương không.
- Output có chứa timestamp hoặc đường dẫn tuyệt đối của máy build không.
- Generated file có được ghi vào đúng thư mục build output không.
- Build sạch có xóa output cũ trước khi tạo lại không.
- Incremental build có cập nhật/xóa file tương ứng khi annotation hoặc schema thay đổi không.
- Có generated file cũ bị giữ lại dù source gốc đã xóa không.

Thông thường không nên chỉnh sửa thủ công generated file. Hãy sửa annotation, schema, template hoặc cấu hình generator rồi chạy lại task. Nếu dự án chủ động commit mã sinh vào repository, cần ghi rõ nguồn, tool version và quy trình tái sinh để tránh sửa output mà không cập nhật input.

### 5.4. Incremental annotation processing

Build tool có thể phân loại processor theo cách ảnh hưởng của input tới output. Trong Gradle, processor có thể khai báo incremental type như `isolating`, `aggregating` hoặc `dynamic` thông qua metadata tương ứng.

- **Isolating:** output của một input element không phụ thuộc vào các element không liên quan khác. Khi một input thay đổi, build tool có thể chỉ xử lý phần tương ứng.
- **Aggregating:** output tổng hợp phụ thuộc vào nhiều input, ví dụ registry hoặc danh sách implementation. Thay đổi một input có thể yêu cầu cập nhật output tổng.
- **Dynamic:** processor khai báo hành vi incremental theo cơ chế động được build tool hỗ trợ.

Chỉ khai báo loại incremental khi processor thực sự tuân thủ hợp đồng đó. Khai báo sai có thể khiến incremental build bỏ sót output cần tạo hoặc không xóa output đã lỗi thời. Khi nâng JDK, compiler plugin hoặc processor, cần chạy cả clean build và incremental build để so sánh kết quả.

## 6. Kiểm tra các công cụ tạo mã ngoài annotation processing

Với OpenAPI Generator, Protobuf, WSDL generator hoặc công cụ tương tự, cần đánh giá cả generator lẫn output:

1. Phiên bản generator có chạy được trên JDK dùng cho build không?
2. Plugin Gradle/Maven có hỗ trợ phiên bản build tool và JDK hiện tại không?
3. Schema/input có thay đổi giữa các lần build không?
4. Generator có template tùy chỉnh hoặc plugin riêng không?
5. Generated source dùng source level và Java API nào?
6. Runtime library được sinh ra cần phiên bản nào?
7. Output có ổn định và tái tạo được không?
8. Có file generated cũ không còn được tham chiếu nhưng vẫn nằm trong source set không?

Ví dụ, nâng OpenAPI Generator có thể thay đổi package, tên method, kiểu date/time, client implementation hoặc JSON annotation. Dù OpenAPI document không đổi, output mới vẫn có thể khác. Cần xem diff generated source và kiểm thử consumer trước khi chấp nhận thay đổi.

Với Protobuf, kiểm tra `protoc`, plugin Java, generated code và protobuf runtime. Schema có thể giữ nguyên nhưng phiên bản generator mới sinh code phụ thuộc API runtime khác. Với SOAP, WSDL/XSD và generated stub cần được kiểm tra cùng phiên bản JAX-WS/JAXB implementation mà ứng dụng thực sự sử dụng; không giả định mọi module vẫn được đóng gói trong JDK như các phiên bản Java cũ.

## 7. Lập ma trận build và runtime cho mã sinh

Đối với dự án hỗ trợ nhiều Java release, nên lập ma trận để xác nhận rõ tổ hợp nào được hỗ trợ.

Ví dụ minh họa:

| Trường hợp | JDK chạy compiler/processor | Release/API target | Runtime kiểm thử | Mục tiêu |
|---|---:|---:|---:|---|
| A | 17 | 17 | 17 | Baseline hiện tại |
| B | 21 | 17 | 17 | Build mới nhưng giữ baseline runtime cũ |
| C | 21 | 21 | 21 | Nâng cả compile target và runtime |
| D | 25 | 21 | 21 | Kiểm tra compiler/processor mới trong khi giữ Java 21 baseline |

Ma trận thực tế phải phản ánh các JDK được dự án cam kết hỗ trợ. Không cần chạy mọi tổ hợp có thể tạo ra; ưu tiên các tổ hợp có thể xuất hiện trong CI, phát hành, triển khai và rollback.

Với mỗi tổ hợp, ghi:

- Gradle/Maven version và JDK chạy build tool.
- JDK toolchain thực thi `javac`.
- Processor/generator version và runtime dependency.
- Source/API release và bytecode target.
- Phiên bản Java tối thiểu dùng để chạy artifact.
- Kết quả clean build, incremental build, test và runtime verification.

## 8. Ví dụ cấu hình và kiểm tra trong Gradle

Ví dụ dưới đây minh họa cách tách toolchain, release target và processor dependency trong dự án Gradle dùng Java plugin:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

dependencies {
    compileOnly 'org.mapstruct:mapstruct:<version>'
    annotationProcessor 'org.mapstruct:mapstruct-processor:<version>'
}
~~~

Trong ví dụ, JDK 21 được dùng làm toolchain biên dịch, còn source/API/bytecode baseline được đặt ở Java 17. MapStruct processor được đặt trong `annotationProcessor`, tách khỏi runtime dependency. Cần kiểm tra phiên bản Gradle, JDK toolchain, MapStruct và các plugin khác có hỗ trợ tổ hợp này.

Nếu test source cũng dùng annotation processing, cấu hình processor cho test source set tương ứng. Nếu có processor riêng cho integrationTest hoặc source set tùy chỉnh, cần cấu hình riêng thay vì giả định nó tự kế thừa cấu hình của `main`.

Sau khi build, kiểm tra generated source directory của task compile và xác nhận source đã được đưa vào compilation. Kiểm tra JAR cuối bằng `jar tf`, sau đó chạy test trên runtime tối thiểu mà dự án cam kết.

## 9. Ví dụ cấu hình và kiểm tra trong Maven

Với Maven Compiler Plugin, processor có thể được khai báo trong `annotationProcessorPaths` để tách đường dẫn processor khỏi compile classpath. Ví dụ cấu trúc:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>${mapstruct.version}</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Đây là cấu trúc minh họa; cần dùng phiên bản Maven Compiler Plugin có hỗ trợ các cấu hình tương ứng và khai báo annotation API/runtime library theo yêu cầu của processor. Nếu dùng nhiều processor, khai báo từng processor và kiểm tra thứ tự/tương tác nếu chúng cùng tạo hoặc đọc generated type.

Đối với JDK 23 trở lên, việc khai báo processor rõ ràng đặc biệt quan trọng do thay đổi mặc định discovery của `javac`. Kiểm tra effective POM và compiler command line để xác nhận processor path thực sự được truyền tới compiler.

## 10. Kiểm tra trong CI và xác minh output

Một pipeline phù hợp có thể thực hiện:

~~~text
Resolve JDK/toolchain và build plugin
              |
              v
Resolve annotation processors / generators
              |
              v
Generate source từ schema/template (nếu có)
              |
              v
Compile + annotation processing theo --release
              |
              v
Kiểm tra generated output và compiler warnings
              |
              v
Unit + integration + runtime tests
              |
              v
Clean/incremental build consistency
              |
              v
Publish build artifact và lưu build metadata
~~~

Nên lưu trong build metadata:

- JDK vendor/version/build dùng cho build.
- Gradle/Maven và compiler plugin version.
- Processor/generator cùng version.
- Source/API release và bytecode target.
- Các option annotation processing quan trọng.
- Schema/template revision và generated source artifact nếu cần audit.

Không nhất thiết commit toàn bộ generated source vào Git. Tuy nhiên, CI cần có cách lưu hoặc tái tạo chính xác output để khi phát sinh lỗi có thể xác định generator hoặc processor nào tạo ra nó.

## 11. Các lỗi thường gặp khi nâng JDK

### Processor không được chạy

Nguyên nhân có thể là processor chỉ nằm trên compile classpath, service metadata sai, processor path bị thiếu hoặc chính sách discovery của JDK mới thay đổi. Hãy kiểm tra compiler arguments và build tool configuration, không chỉ kiểm tra dependency có mặt.

### Processor lỗi khi khởi tạo hoặc truy cập compiler internals

Nguyên nhân thường là processor cũ dùng API nội bộ của `javac`, reflection hoặc giả định về AST. Cần nâng processor lên bản hỗ trợ JDK đích và kiểm tra release notes. Chỉ dùng `--add-exports`/`--add-opens` khi vendor hướng dẫn và có phạm vi giới hạn.

### Generated source không biên dịch

Nguyên nhân có thể là processor chưa hiểu source version mới, generator sinh cú pháp/API vượt quá `--release`, hoặc runtime dependency không tương thích. Hãy đọc generated source, xem lỗi compiler ở file được sinh và xác định nguồn tạo file trước khi sửa.

### Generated output khác giữa clean và incremental build

Nguyên nhân có thể là metadata incremental không chính xác, processor phụ thuộc thứ tự không ổn định, output cũ chưa bị xóa hoặc task dependency chưa khai báo đủ. So sánh output của hai chế độ, kiểm tra input/output declaration và nâng processor/build plugin nếu cần.

### Build thành công nhưng runtime lỗi

Generated code có thể gọi API không có trên runtime thấp nhất, cần runtime dependency chưa được đóng gói hoặc tạo metadata mà framework mới đọc khác đi. Hãy chạy test trên runtime target, kiểm tra dependency tree và artifact cuối cùng thay vì chỉ kiểm tra compile task.

## 12. Checklist đánh giá mã sinh và processor theo phiên bản Java

- [ ] Đã liệt kê mọi generator chạy trước compiler và mọi annotation processor.
- [ ] Đã phân biệt annotation compile-time, generated output và runtime dependency.
- [ ] Đã xác định JDK chạy build tool và JDK toolchain chạy compiler/processor.
- [ ] Đã xác định source/API release, bytecode target và runtime tối thiểu.
- [ ] Đã kiểm tra ma trận hỗ trợ JDK của đúng phiên bản processor/generator.
- [ ] Đã xác minh processor discovery, processor path/module path và service metadata.
- [ ] Đã rà soát phụ thuộc vào `com.sun.tools.javac.*`, reflection và compiler internals.
- [ ] Đã kiểm tra `SourceVersion` và cách processor xử lý construct ngôn ngữ mới.
- [ ] Đã kiểm tra generated source có dùng cú pháp/API phù hợp release target.
- [ ] Đã xác nhận runtime dependency và generated classes được đóng gói đúng.
- [ ] Đã kiểm tra clean build, incremental build và output tái tạo.
- [ ] Đã chạy test trên JDK đích và runtime tối thiểu được hỗ trợ.
- [ ] Đã lưu processor/generator version, compiler options và kết quả kiểm thử trong CI.

## 13. Kết luận

Đánh giá mã sinh và annotation processor phải xem cả công cụ, môi trường chạy công cụ và output cuối cùng. JDK chạy compiler quyết định môi trường mà processor thực thi; `--release` quyết định source/API/bytecode baseline của mã được biên dịch; runtime tối thiểu quyết định output có thể chạy ở đâu. Ba yếu tố này có thể khác nhau và cần được ghi riêng.

Khi nâng Java, hãy xác minh processor/generator theo tài liệu hỗ trợ của đúng phiên bản, cấu hình discovery tường minh, rà soát việc sử dụng compiler internals, kiểm tra source sinh ra và chạy cả clean/incremental build. Chỉ khi generated output được biên dịch, đóng gói và chạy đúng trên các JDK mục tiêu, nhóm mới có đủ bằng chứng để chấp nhận thay đổi trong lộ trình migration.
