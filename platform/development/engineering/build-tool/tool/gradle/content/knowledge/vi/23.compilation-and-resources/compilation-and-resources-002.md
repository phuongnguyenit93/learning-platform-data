# Biên dịch tăng dần, compile avoidance và ranh giới thay đổi API

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Biên dịch và tài nguyên

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt chính xác **incremental build**, **incremental Java compilation**, **Java compile avoidance**, **build cache** và **configuration cache** — năm khái niệm có liên quan nhưng không thay thế nhau.
2. Hiểu **Application Binary Interface (ABI)** là gì, vì sao thay đổi thân phương thức/private implementation thường không buộc module phụ thuộc phải biên dịch lại, còn thay đổi API/ABI có thể buộc Gradle phân tích và biên dịch những nguồn bị ảnh hưởng.
3. Giải thích Gradle sử dụng **compile classpath normalization, classpath snapshots** và dependency analysis như thế nào để quyết định bỏ qua toàn bộ JavaCompile task hoặc chỉ biên dịch một phần source files.
4. Chọn đúng **api** và **implementation** với Java Library Plugin để giảm compile classpath bị rò rỉ, tạo ranh giới thay đổi hợp lý và hạn chế recompilation dây chuyền.
5. Biết các thay đổi cần chú ý: public/protected signatures, superclass/interface, generic signatures, public compile-time constants, annotation/annotation processors, JPMS exports, generated sources và JDK/compiler options.
6. Tạo và chạy bài lab **Gradle Groovy DSL + Java 17** gồm project :core và :app; thử sửa một implementation method body, xác nhận compile avoidance, sau đó đổi public method signature để quan sát compilation bị ảnh hưởng.
7. Đọc đúng **UP-TO-DATE, FROM-CACHE, NO-SOURCE, SKIPPED** và logs khi chạy Gradle; không kết luận “incremental compilation đã xảy ra” chỉ vì thấy task UP-TO-DATE.
8. Xây dựng checklist tìm nguyên nhân khi một code change nhỏ khiến nhiều JavaCompile tasks chạy lại, đồng thời biết giới hạn khi dùng processors hoặc plugins ngoài.

**Ý chính:** Gradle tiết kiệm thời gian ở nhiều tầng. Nếu task inputs/outputs không đổi, nó có thể **bỏ qua task**; với JavaCompile, nếu classpath dependency chỉ đổi phần **không ảnh hưởng ABI**, Gradle có thể **tránh biên dịch downstream project**; nếu JavaCompile phải chạy, incremental compiler có thể **chỉ biên dịch những Java source files chịu ảnh hưởng**. Các tầng này khác với việc khôi phục outputs từ build cache.

## 1. Năm cơ chế thường bị gọi chung là “biên dịch tăng dần”

| Cơ chế | Câu hỏi Gradle đang trả lời | Kết quả đặc trưng |
|---|---|---|
| **Incremental build / up-to-date check** | Task inputs và outputs có thay đổi đủ để phải chạy task không? | Task có thể được đánh dấu **UP-TO-DATE**, không chạy task actions |
| **Compile avoidance (Java)** | Bytecode của dependency đổi nhưng **ABI trên compile classpath có đổi không**? | JavaCompile task của consumer có thể **UP-TO-DATE** dù implementation ở dependency đã đổi |
| **Incremental Java compilation** | Khi JavaCompile cần chạy, **source classes nào bị ảnh hưởng**? | Compiler có thể biên dịch **một tập con** của Java sources |
| **Build cache** | Task outputs có thể lấy lại từ cache bằng cache key tương thích không? | Task có thể **FROM-CACHE**; outputs được khôi phục thay vì thực thi compilation |
| **Configuration cache** | Có thể tái sử dụng mô hình task/configuration từ lần chạy trước không? | Tránh lặp lại một phần configuration phase; **không tự bảo đảm** compileJava không chạy |

Cần tách **incremental build** và **incremental compilation**:
- Incremental build là cơ chế chung cho tasks có input/output được mô hình hóa.
- Incremental compilation là khả năng đặc thù của Java compiler integration, khi task **đã phải thực thi**.
- Compile avoidance là cách Gradle coi **thay đổi không ảnh hưởng ABI** trên compile classpath như không cần tái biên dịch consumer.
- Build cache có thể trả kết quả của một task cần chạy thay vì chạy compiler, với điều kiện task/cache key phù hợp.
- Configuration cache chủ yếu rút ngắn thời gian Gradle xây task graph, không phải kỹ thuật phân tích ABI.

**Ví dụ:** Bạn sửa implementation của một phương thức trong :core. :core:compileJava có thể chạy theo incremental compilation; :app:compileJava có thể UP-TO-DATE do compile avoidance; :app:run vẫn chạy và in kết quả logic mới. Nếu bật cache và cache key khớp một kết quả cũ, một task khác cũng có thể FROM-CACHE. Không nên gộp cả ba kết quả thành một câu “Gradle biên dịch tăng dần”.

## 2. Incremental build: tầng task có thay đổi hay không?

Gradle kiểm tra inputs và outputs do mỗi task công bố. Với JavaCompile, các input quan trọng gồm Java source files, compile classpath theo normalization tương ứng, compiler options/toolchain và những input khác mà Gradle biết tác động đến kết quả. Outputs bao gồm các .class files được tạo.

Quy trình khái niệm:

~~~text
Task :core:compileJava
    |
    +-- Sources: Greeter.java, Prefix.java, Calculator.java
    +-- Compile classpath + Java toolchain/arguments
    +-- Compiler/task implementation
    |
    v
So sánh trạng thái lần build trước:
    |
    +-- Không có thay đổi ảnh hưởng output + output còn hợp lệ
    |       -> UP-TO-DATE
    |
    +-- Input/output thay đổi
            -> Phải xử lý task
               -> Có thể FROM-CACHE nếu cache key khớp
               -> Hoặc execute JavaCompile
                  -> Có thể compile incremental nếu đủ điều kiện
~~~

Một custom task không khai báo inputs/outputs chính xác sẽ làm Gradle khó đưa ra quyết định tối ưu hoặc tệ hơn là báo up-to-date sai. Đối với JavaCompile chuẩn của Java Plugin, Gradle đã mô hình hóa nhiều inputs/outputs và hỗ trợ compile avoidance/incremental compilation.

### 2.1. Các nhãn outcome thường thấy

| Nhãn | Ý nghĩa | Không nên suy ra |
|---|---|---|
| **UP-TO-DATE** | Task actions không chạy vì trạng thái input/output được coi là vẫn hợp lệ | Không chứng minh compiler đã biên dịch vài source |
| **FROM-CACHE** | Kết quả task được phục hồi từ build cache | Không chứng minh source vừa được biên dịch trên máy hiện tại |
| **NO-SOURCE** | Task không có source files cần xử lý | Không có nghĩa compile avoidance phân tích ABI thành công |
| **SKIPPED** | Task bị bỏ qua bởi điều kiện hoặc quy tắc khác | Không đồng nghĩa UP-TO-DATE |
| Không có nhãn outcome riêng | Task chạy bình thường | Không biết nó biên dịch toàn bộ hay một phần source cho tới khi xem logs/thông tin khác |
| **FAILED** | Task thực thi hoặc xử lý đầu vào thất bại | Không tự nói lỗi nằm ở compile, repository hay configuration |

Dùng:

~~~bash
./gradlew :app:compileJava --console=plain --info
~~~

để xem lifecycle và chi tiết phù hợp. Với các Gradle versions mới, output có thể thay đổi tên hoặc mức độ logging; hãy kiểm chứng trạng thái task thực tế, đừng dựa vào một dòng mẫu từ phiên bản khác.

### 2.2. Vì sao clean làm phép thử khác?

~~~bash
./gradlew clean :app:compileJava
~~~

Sau clean, các outputs cũ có thể bị xóa nên Gradle không còn điều kiện để giữ trạng thái UP-TO-DATE như lượt build ngay trước. Nếu cache bật, task cũng có thể FROM-CACHE; nếu cache tắt, compiler phải dựng lại outputs. Vì vậy, để **đo incremental/compile avoidance**, đừng clean giữa mọi lượt thử; hãy chạy baseline, chạy lại, thay đổi đúng một file rồi chạy lại.

Tương tự:
- **--rerun-tasks** ép tasks chạy, không phù hợp để chứng minh chúng đáng ra được UP-TO-DATE.
- **--no-build-cache** tạm ngăn cache che kết quả thử nghiệm, hữu ích khi muốn quan sát up-to-date/compilation.
- **--refresh-dependencies** kiểm tra lại dependency metadata/artifacts, không phải công tắc bật incremental compilation.
- **--offline** chỉ tác động nguồn resolve dependencies, không tự điều khiển phân tích ABI.

## 3. Compile avoidance: tránh biên dịch downstream khi ABI không đổi

Gradle JavaCompile xử lý compile classpath khác runtime classpath. Khi thư viện đã biên dịch đổi .class files, Gradle có thể so sánh **ABI** của các class trên compile classpath thay vì xem toàn bộ bytes như input nhạy cảm.

Nếu ABI không đổi, compiler của module phụ thuộc không cần chạy lại chỉ vì implementation bytes khác. Đó là **Java compile avoidance**.

### 3.1. Ví dụ đơn giản

**Phiên bản A của library:**

~~~java
package demo.core;

public final class PriceService {
    public static int price() {
        return 100;
    }
}
~~~

**Phiên bản B:**

~~~java
package demo.core;

public final class PriceService {
    public static int price() {
        int base = 120;
        return base - 20;
    }
}
~~~

Cả hai có public method price() trả int, không đổi chữ ký public. Bytecode method body khác nhưng ABI cần thiết cho consumer **vẫn như nhau**. Với compile classpath đúng cách và điều kiện tối ưu được đáp ứng, module dùng PriceService.price() có thể **không cần biên dịch lại**. Khi chạy, JVM vẫn nạp implementation đã build của library.

Đây là **snippet minh họa**, không phải ví dụ chạy độc lập; bài lab đầy đủ ở mục 7 sẽ cho thấy task outcomes.

### 3.2. ABI là gì?

**Application Binary Interface (ABI)** là những thông tin ở mức compiled class mà code khác cần để biên dịch/liên kết chống lại library, chẳng hạn:

- Tên và khả năng truy cập của lớp, interface hoặc record được expose.
- Hệ kế thừa: superclass, implemented interfaces và các quan hệ type quan trọng.
- Public/protected method signatures: tên, tham số, kiểu trả về, static/instance, visibility và các đặc tính liên quan.
- Public/protected fields: kiểu, tên, visibility và thông tin constant có liên quan.
- Generic type signatures dùng trong public API.
- Một số metadata annotations/type information ảnh hưởng compiler và tooling.
- Compile-time constants mà consumer có thể **inline**.
- Java module descriptors/exports theo các quy tắc JPMS và toolchain.

**Không đơn giản bằng câu “mọi dòng public luôn là ABI, private luôn không”.** Gradle trích xuất ABI từ bytecode với những quy tắc của Java và classpath normalization; có các tình huống package-private/split package, compiler-generated methods, annotations hoặc constants cần chú ý. Hãy dùng ví dụ được kiểm tra thực tế và công cụ Gradle để xác nhận.

### 3.3. Những thay đổi thường không phá ABI

| Thay đổi | Vì sao downstream compile thường tránh được? |
|---|---|
| Đổi method body nhưng giữ nguyên signature | Compiler consumer vẫn thấy cùng contract để compile |
| Thêm/sửa private method hoặc field | Chi tiết private không thuộc API cần của consumer |
| Thay đổi local variable, control flow | Không làm thay chữ ký public/protected |
| Sửa comment/Javadoc trong source | Không nhất thiết làm thay compiled public ABI |
| Đổi tên tham số | JVM method descriptor và phần lớn ABI không dựa vào tên tham số |
| Sửa resource của library | Resource thường không đổi Java compile ABI; nhưng có thể đổi runtime behavior |
| Thay đổi tên/path JAR không đổi ABI | Compile classpath normalization có thể coi nó tương đương về ABI, tùy metadata và input model |

Các thay đổi này **không bảo đảm mọi task trong build được UP-TO-DATE**. Task :core:compileJava vẫn có thể thực thi vì source của core đổi; :core:jar và :app:run có thể cần chạy để phản ánh implementation mới. Compile avoidance chủ yếu nói về **consumer JavaCompile**.

### 3.4. Những thay đổi có thể ảnh hưởng ABI

| Thay đổi | Tác động có thể có |
|---|---|
| Xóa hoặc đổi tên public method | Caller cũ có thể không compile; consumer cần được kiểm tra lại |
| Đổi kiểu tham số hoặc kiểu trả về | Method descriptor/signature thay đổi; caller/implementor chịu ảnh hưởng |
| Đổi class/interface hierarchy | Type assignability và method resolution của consumer có thể thay đổi |
| Đổi public/protected visibility, static/final | Có thể thay đổi cách code khác truy cập hoặc kế thừa |
| Thay đổi public generic signature | Java compiler/IDE có thể chịu tác động ngay cả khi một số erased descriptors giống |
| Thay/loại public field | Consumer đang dùng field có thể fail compile |
| Thay compile-time constant public | Code Java có thể inline giá trị và cần biên dịch lại để nhận giá trị mới |
| Thay annotation/type metadata ảnh hưởng compilation | Compiler hoặc processor có thể cần xem xét lại source |
| Thay module-info exports/requires transitive | JPMS compilation boundary có thể thay đổi |
| Thêm/đổi public API types | ABI snapshot đổi; Gradle đánh giá lại JavaCompile phụ thuộc, dù incremental compiler có thể thu hẹp nguồn cần recompile |

**API change không luôn đồng nghĩa biên dịch toàn bộ downstream module.** Compile avoidance không thể bỏ qua thay đổi ABI **như một đơn vị nguyên vẹn**, nhưng incremental compiler có thể xác định những source files chịu ảnh hưởng. Ví dụ thêm một overload công khai có thể đổi ABI nhưng không làm những lời gọi hiện hữu bị lỗi; số file thực sự cần biên dịch phụ thuộc dependency analysis.

### 3.5. ABI-compatible không đồng nghĩa behavior-compatible

Một method body đổi từ tính thuế 10% sang 20%, ABI có thể giữ nguyên và consumer compile được bỏ qua. Nhưng đó vẫn là **behavior change**, có thể làm integration tests và runtime results thay đổi.

Vì vậy không dùng compile avoidance như tiêu chuẩn đánh giá SemVer hoặc bảo đảm API logic không đổi. Nó chỉ trả lời một câu hỏi hẹp hơn: **có cần chạy lại Java compiler của consumer do compile classpath change này không?**

## 4. Incremental Java compilation: khi task chạy thì compile bao nhiêu nguồn?

Trong Gradle hiện đại, **incremental Java compilation được bật theo mặc định** cho JavaCompile trong các điều kiện được hỗ trợ. Nó phân tích class dependency graph và chỉ compile những nguồn bị thay đổi hoặc phụ thuộc vào thay đổi quan trọng.

### 4.1. Ví dụ cùng một module

~~~text
:core/src/main/java/
    demo/core/Greeter.java
    demo/core/Prefix.java
    demo/core/Calculator.java
~~~

Quan hệ:

~~~text
Greeter.java --> dùng Prefix.text()
Calculator.java --> độc lập
~~~

Nếu chỉ sửa body của Prefix.text() mà không sửa ABI:
- **:core:compileJava** cần xử lý vì source Prefix.java đổi.
- Java incremental compiler có thể chỉ biên dịch Prefix.java thay vì mọi file trong :core.
- Greeter.java và Calculator.java không nhất thiết phải biên dịch lại nếu compiler có đủ dữ liệu phụ thuộc và thay đổi không ảnh hưởng ABI.
- **:app:compileJava** có thể được bỏ qua hoàn toàn nhờ compile avoidance nếu ABI của :core không đổi.

Sơ đồ này làm rõ **hai tầng**: giới hạn source files trong producer **và** bỏ qua compilation ở consumer.

### 4.2. Bật cấu hình tường minh nếu muốn

Với Java plugin và Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.incremental = true
    options.encoding = 'UTF-8'
}
~~~

Đối với Gradle 4.10+ và các bản hiện đại, incremental Java compilation đã được bật mặc định. Dòng options.incremental = true trong lab dùng để **diễn đạt ý định rõ ràng**, không phải yêu cầu đặc biệt để compile avoidance hoạt động.

**Không áp dụng kết luận tương tự máy móc cho Kotlin, Groovy, Scala hoặc Android Gradle Plugin.** Mỗi plugin/compiler có mô hình incremental và giới hạn riêng; bài này tập trung **JavaCompile** của Gradle Java ecosystem.

### 4.3. Khi nào Gradle có thể phải compile rộng hơn?

- Lần đầu build, sau clean hoặc khi thiếu compiler analysis history.
- Thay đổi compiler options/JDK/toolchain có thể ảnh hưởng nhiều outputs.
- Source phụ thuộc tới class có ABI thay đổi.
- Annotation processor không incremental hoặc processor đổi implementation.
- Source generation, public constants, dependency graph, tool compiler behavior không cho phép thu hẹp an toàn.
- Classpath thiếu metadata hoặc tình huống Kotlin/Groovy/Java mixed compilation được plugin xử lý khác.
- Một build custom can thiệp inputs/outputs của JavaCompile, làm mất khả năng phân tích đáng tin.

Không nên viết “incremental compilation luôn compile đúng một file” vì javac có quan hệ phụ thuộc giữa source classes và Gradle có các trường hợp conservatively recompiling nhiều classes.

### 4.4. Incremental sau compile failure

Nếu biên dịch trước đó **thất bại**, Gradle có thể không giữ được cùng trạng thái hợp lệ như một compilation đã thành công. Các phiên bản Gradle có tùy chọn incrementalAfterFailure với điều kiện/đặc tính riêng. Khi thử nghiệm incremental compilation, dùng **baseline đã compile thành công** rồi thực hiện một thay đổi nhỏ; đừng dựa vào lần build thất bại làm bằng chứng đã có cache analysis đầy đủ.

## 5. Java Library Plugin: api/implementation tạo ranh giới thay đổi

Một module thư viện nên áp:

~~~groovy
plugins {
    id 'java-library'
}
~~~

thay vì chỉ dùng java khi cần thể hiện ranh giới **public API dependencies** và **implementation dependencies**.

### 5.1. Cách khai báo

~~~groovy
dependencies {
    api 'com.example:public-contracts:1.0'
    implementation 'com.example:internal-codec:1.0'
}
~~~

Hai tọa độ com.example chỉ minh họa cách phân loại, **không được bảo đảm tồn tại** trên Maven Central.

- **api**: dependency chứa type mà consumer cần khi compile against library API; thường được expose qua apiElements.
- **implementation**: dependency được library dùng nội bộ; consumer Java compile thông thường không nhận dependency đó qua apiElements, nhưng consumer runtime cần nó qua runtimeElements.
- **runtimeOnly**: dependency được cần lúc chạy, không đưa vào compile classpath của chính library.
- **compileOnlyApi**: public compile-time contract có thể được consumer nhìn thấy khi compile nhưng không tự đưa vào runtime.
- **compileOnly**: phục vụ compile của module, không expose sang compile hoặc runtime consumer.

### 5.2. Vì sao điều này giúp compile avoidance?

Giả sử:

~~~text
:app
  implementation project(':service')

:service (java-library)
  api project(':contracts')
  implementation project(':codec')
~~~

Nếu :codec thay đổi implementation hoặc version nhưng không làm **public ABI của :service** đổi:
- :service có thể cần compile/test/run lại tùy ảnh hưởng.
- :app:compileClasspath không bị lộ :codec chỉ vì :service sử dụng nó nội bộ.
- Compile classpath nhỏ hơn, ít artifact metadata/ABI changes bị kéo sang consumer.
- :app:compileJava có nhiều cơ hội **UP-TO-DATE** hơn.
- :app runtimeClasspath vẫn có thể nhận :codec qua runtimeElements, vì code chạy của :service cần nó.

**Không biến every dependency thành api** để sửa một lỗi import. Nếu app thực sự dùng class từ :codec, app nên khai báo dependency trực tiếp hoặc xem lại thiết kế public API; nếu class từ :codec là một phần hợp đồng public của :service, service phải khai báo api phù hợp.

### 5.3. Khi nào bắt buộc cân nhắc api?

Nếu public method của service trả một type từ dependency khác:

~~~java
// Ví dụ minh họa API, không thuộc lab chính.
public com.example.contracts.Result load(String key) {
    // ...
}
~~~

Consumer muốn compile một method như vậy phải nhìn thấy type Result. Nếu module contracts chỉ khai báo implementation trong service, consumer có thể báo missing type. Khi hợp đồng API thực sự expose Result, **api** là lựa chọn phù hợp của java-library.

Ngược lại, nếu service chỉ dùng thư viện nội bộ bên trong method body và public API chỉ dùng String/int/JDK types, dùng **implementation** để giảm rò rỉ dependency.

### 5.4. apiElements và runtimeElements

Trong mô hình Java Library:

~~~text
:app compileClasspath
    |
    +--> :service apiElements
            |
            +-- API types và api dependencies
            +-- Không đưa implementation dependencies vào consumer compile

:app runtimeClasspath
    |
    +--> :service runtimeElements
            |
            +-- Runtime artifact/classes của :service
            +-- api + implementation + runtimeOnly theo variant phù hợp
~~~

Gradle chọn variants qua attributes của consumer và producer. Không khẳng định project dependency **luôn bắt buộc tạo JAR** trước khi app compile: Gradle có thể chọn classes output hoặc artifact theo khả năng và variant. Điều đúng là producer/consumer task dependencies được nối theo mô hình Gradle.

### 5.5. Việc chuyển implementation thành api có thể là thay đổi lớn

Ngay cả khi code Java không đổi, thay một dependency từ implementation sang api làm **consumer compile classpath** đổi:
- Consumer có thể nhìn thấy thêm types, nên coupling tăng.
- Graph/version conflict ở compile classpath của consumer có thể thay đổi.
- Compile avoidance và up-to-date checks có thể bị ảnh hưởng.
- Published Gradle Module Metadata/Maven POM scopes có thể đổi.

Do đó review api vs implementation như **một phần kiến trúc module**, không chỉ tối ưu tốc độ.

## 6. Ranh giới API, public constants và các trường hợp tinh tế

### 6.1. Public method body với public signature

**Phiên bản A:**

~~~java
public static String greet(String name) {
    return "Hello, " + name;
}
~~~

**Phiên bản B:**

~~~java
public static String greet(String name) {
    return "Hi, " + name;
}
~~~

Signature public không đổi, compile ABI có thể giữ nguyên. Downstream JavaCompile có thể được bỏ qua, nhưng runtime output thay đổi. Đây là **điểm mạnh của compile avoidance** chứ không phải lỗi.

### 6.2. Đổi tham số/return type

~~~java
// Cũ:
public static String greet(String name)

// Mới:
public static String greet(String prefix, String name)
~~~

Code đã compile source gọi greet("Lan") cần được biên dịch lại để phát hiện không còn overload phù hợp. Gradle phải coi sự thay đổi public signature là thay đổi ABI. Nếu app source chưa sửa, :app:compileJava có thể **FAILED** với lỗi không khớp method; đây là hành vi bảo vệ build.

**Không kết luận “compile avoidance hỏng”.** Nó không được phép bỏ qua mọi API change.

### 6.3. Compile-time constants có thể bị inline

~~~java
package demo.core;

public final class Constants {
    public static final int RETRY_LIMIT = 3;

    private Constants() {
    }
}
~~~

Nếu consumer code có:

~~~java
int attempts = Constants.RETRY_LIMIT;
~~~

javac có thể **inline** giá trị 3 vào bytecode consumer. Khi đổi RETRY_LIMIT từ 3 thành 4, signature field có thể vẫn nhìn giống trước, nhưng giá trị constant tác động tới kết quả đã biên dịch. Gradle có cơ chế xem xét constant value và dependencies để đảm bảo các source bị ảnh hưởng được recompile khi cần.

**Kết luận thiết kế:** Đừng phơi bày các hằng số public compile-time nếu bạn dự định thường xuyên đổi giá trị mà vẫn đòi consumers nhận ngay hành vi mới mà không rebuild. Cân nhắc accessor method cho giá trị có thể thay đổi:

~~~java
public static int retryLimit() {
    return 3;
}
~~~

Việc đổi method body có thể không buộc consumer recompile; nhưng để nhận giá trị mới, consumer vẫn phải **chạy với phiên bản library mới**.

### 6.4. Generic, annotations, records và JPMS

ABI không chỉ là raw JVM method descriptor:
- Generic signatures trong public API có thể quan trọng với Java source compilation.
- Public annotations có thể ảnh hưởng compiler, reflection hoặc processors; RetentionPolicy cũng quyết định runtime behavior.
- Record component changes tác động constructor/accessors mà consumer dùng.
- Sealed class permits hierarchy ảnh hưởng type restrictions.
- module-info.java exports/requires transitive thay đổi khả năng truy cập ở module path.

Tuy nhiên, kết quả compile avoidance chi tiết của mỗi thay đổi phải được quan sát với **Gradle + Java toolchain cụ thể**. Không chuyển một quy tắc đơn giản như “đổi comment không đổi ABI” thành mệnh đề mọi metadata change đều bị bỏ qua.

### 6.5. Source compatibility, binary compatibility và behavioral compatibility

| Loại tương thích | Câu hỏi |
|---|---|
| **Source compatibility** | Source consumer cũ có compile được khi dùng API mới không? |
| **Binary compatibility** | Bytecode consumer đã compile trước đó có liên kết/chạy với library mới không? |
| **Behavioral compatibility** | Kết quả/hành vi còn đáp ứng kỳ vọng người dùng không? |
| **Gradle compile avoidance** | ABI input của JavaCompile có thay đổi đủ để phải compile lại không? |

Các câu hỏi có liên quan nhưng **không đồng nhất**. Một method body change có thể giữ ABI nhưng phá business rules. Một public method mới thêm vào có thể không phá source compatibility nhưng đổi ABI snapshot. Một method xóa đi có thể khiến code cũ lỗi compiler và bytecode consumer cũ lỗi NoSuchMethodError khi chạy.

## 7. Bài lab hoàn chỉnh: Java 17 multi-project Gradle

Bài lab không dùng external Java dependencies, nên bạn có thể quan sát build/task graph mà không bị download thư viện làm nhiễu. Cần JDK 17, Gradle version hỗ trợ Java 17 hoặc Gradle Wrapper được tạo/đã có. Dùng **Groovy DSL**.

### 7.1. Cấu trúc thư mục

~~~text
compile-boundary-lab/
├── settings.gradle
├── gradlew                       # sau khi tạo Gradle Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/
│       ├── Greeter.java
│       ├── Prefix.java
│       └── Calculator.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

**core** là Java library. **app** là Java application chỉ sử dụng public API của core. Package-private Prefix là implementation detail, còn Calculator độc lập để minh họa không phải mọi source đều liên quan tới một thay đổi nhỏ.

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'compile-boundary-lab'
include('core', 'app')
~~~

Gradle project paths là :core và :app. Nếu không include, implementation project(':core') ở app/build.gradle sẽ không resolve được.

### 7.3. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    // Java incremental compilation đã được bật mặc định trong Gradle mới.
    options.incremental = true
}
~~~

Không cần Maven Central cho source code này vì core không khai báo dependency ngoài. java-library cho phép core công bố API/implementation variants theo chuẩn Java.

### 7.4. core/src/main/java/demo/core/Prefix.java

~~~java
package demo.core;

final class Prefix {
    private Prefix() {
    }

    static String text() {
        return "Hello, ";
    }
}
~~~

Prefix **không public**; consumer app không import nó. Đổi method body của Prefix là thay đổi implementation của core.

### 7.5. core/src/main/java/demo/core/Greeter.java

~~~java
package demo.core;

import java.util.Objects;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        String trimmed = Objects.requireNonNull(name, "name").strip();
        return Prefix.text() + trimmed;
    }
}
~~~

Public API của core có:
- Class Greeter.
- Public static method greet(String): String.

Nó **không expose Prefix type** trong signature; Prefix là một chi tiết nội bộ. Nếu Prefix.text() thay đổi behavior nhưng không thay ABI, public method signature của Greeter vẫn như cũ.

### 7.6. core/src/main/java/demo/core/Calculator.java

~~~java
package demo.core;

public final class Calculator {
    private Calculator() {
    }

    public static int twice(int value) {
        return value * 2;
    }
}
~~~

Calculator không phụ thuộc Prefix/Greeter. Trong phần thử incremental compilation, đây là class để lý giải vì sao compiler có thể tránh biên dịch lại một nguồn không liên quan.

### 7.7. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.incremental = true
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':core')
}
~~~

application plugin mang Java model, task run và JavaCompile cho app. App dùng **project dependency** tới core, Gradle tự nối producer outputs với consumer compile/runtime classpath; không cần chép JAR core sang app/libs.

### 7.8. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.core.Calculator;
import demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Gradle"));
        System.out.println("twice=" + Calculator.twice(3));
    }
}
~~~

App chỉ thấy Greeter và Calculator public API. Nó không thể import Prefix vì Prefix là package-private và app ở package khác.

### 7.9. Bước A — baseline compile/run

Nếu đã có Gradle Wrapper, từ root:

~~~bash
./gradlew :app:run --console=plain --no-build-cache
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:run --console=plain --no-build-cache
~~~

**Hai dòng stdout từ Main.main** là:

~~~text
Hello, Gradle
twice=6
~~~

Task output của Gradle (ví dụ :core:compileJava, :app:compileJava, :app:run) có thể xuất hiện xung quanh stdout Java. Không hardcode task status ở lần đầu vì phụ thuộc trạng thái build cache/outputs sẵn có.

**Giải thích:** Gradle compile core, compile app dựa trên core API rồi chạy app. Cả hai modules dùng JDK 17 toolchain.

### 7.10. Bước B — chạy lại không sửa gì

~~~bash
./gradlew :app:compileJava --console=plain --no-build-cache
~~~

Vì không có thay đổi hợp lệ nào ảnh hưởng inputs/outputs và lần chạy trước thành công, bạn thường sẽ thấy:

~~~text
> Task :core:compileJava UP-TO-DATE
> Task :app:compileJava UP-TO-DATE
~~~

Có thể có thêm các tasks khác (jar/processResources/classes) và thứ tự cụ thể của output tùy Gradle version; hai dòng trên là trạng thái minh họa kỳ vọng của compiler tasks trong môi trường ổn định.

**Đây là incremental build/up-to-date check**, không chứng minh compiler vừa biên dịch từng file. Khi task UP-TO-DATE, Java compiler **không cần chạy**.

### 7.11. Bước C — thay duy nhất implementation method body

Chỉ sửa file **core/src/main/java/demo/core/Prefix.java**:

~~~java
package demo.core;

final class Prefix {
    private Prefix() {
    }

    static String text() {
        return "Hi, ";
    }
}
~~~

**Không sửa** Greeter.java, Calculator.java, app/Main.java hoặc build.gradle.

Chạy:

~~~bash
./gradlew :app:run --console=plain --no-build-cache --info
~~~

Kỳ vọng trong điều kiện Gradle Java compilation mặc định, build state còn và không có tác nhân khác làm thay đổi inputs:
- :core:compileJava cần xử lý source Prefix.java mới; incremental compiler có thể thu hẹp phạm vi source recompilation.
- :app:compileJava có thể hiển thị **UP-TO-DATE** nhờ compile avoidance: compiled ABI của core mà app nhìn thấy không đổi.
- :app:run vẫn chạy và sử dụng runtime output mới của core.
- Các tasks như :core:jar hoặc processResources có thể có outcomes khác nhau tùy đường dùng classes/artifact.

**Stdout Java sau thay đổi:**

~~~text
Hi, Gradle
twice=6
~~~

Tại sao app dùng implementation mới dù app không recompile? Vì Main.class vẫn gọi Greeter.greet(String), một method với chữ ký không đổi; lúc chạy, class loader nhận Greeter/Prefix classes mới của core. Compile avoidance **không đóng băng behavior** của runtime.

### 7.12. Bước D — kiểm tra ranh giới public API

Bây giờ thay **core/src/main/java/demo/core/Greeter.java** bằng phiên bản **cố ý phá chữ ký cũ**:

~~~java
package demo.core;

import java.util.Objects;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String prefix, String name) {
        String safePrefix = Objects.requireNonNull(prefix, "prefix");
        String safeName = Objects.requireNonNull(name, "name").strip();
        return safePrefix + safeName;
    }
}
~~~

Method greet(String) **đã bị xóa**, thay bằng greet(String,String). App/Main.java **vẫn gọi greet("Gradle")**, nên source consumer không còn hợp lệ với public API mới.

Chạy:

~~~bash
./gradlew :app:compileJava --console=plain --no-build-cache
~~~

Kỳ vọng:
1. :core:compileJava xử lý Greeter.java mới.
2. Gradle nhận thấy ABI core thay đổi; không thể dùng lý do “ABI vẫn như cũ” để bỏ qua app compilation.
3. :app:compileJava chạy/kiểm tra source bị ảnh hưởng và **FAILED** vì lời gọi greet(String) không khớp greet(String,String).

Dạng lỗi javac có thể nói:

~~~text
method greet in class Greeter cannot be applied to given types;
  required: String,String
  found:    String
~~~

Đây là **trích yếu thông tin lỗi**, không phải bản sao toàn bộ log javac; số dòng/vị trí/thông báo thay đổi theo JDK và Gradle version. Điều chắc chắn là lỗi **source compilation** khi method một tham số không còn tồn tại.

### 7.13. Bước E — sửa consumer theo API mới

Sửa **app/src/main/java/demo/app/Main.java**:

~~~java
package demo.app;

import demo.core.Calculator;
import demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Hello, ", "Gradle"));
        System.out.println("twice=" + Calculator.twice(3));
    }
}
~~~

Sau đó:

~~~bash
./gradlew :app:run --console=plain --no-build-cache
~~~

**Stdout từ Main.main:**

~~~text
Hello, Gradle
twice=6
~~~

App được biên dịch lại vì source nó đổi để khớp chữ ký mới. Một build dùng Java incremental compilation có thể chỉ compile Main.java thay vì mọi source file của app nếu app có nhiều file và dependency analysis cho phép; ở lab app chỉ có một source nên không có cơ sở để nói “app compile được đúng một file nhờ incremental compilation”.

### 7.14. Kết quả cần quan sát theo từng bước

| Lượt | Thay đổi | :core:compileJava | :app:compileJava | Chương trình |
|---|---|---|---|---|
| A | Build đầu | Chạy nếu chưa có outputs hợp lệ | Chạy nếu chưa có outputs hợp lệ | Hello, Gradle / twice=6 |
| B | Không đổi gì | Thường UP-TO-DATE | Thường UP-TO-DATE | Không cần chạy Main nếu chỉ gọi compileJava |
| C | Prefix.text() body: Hello → Hi | Cần xử lý source thay đổi; có thể incremental | **Thường UP-TO-DATE** nếu ABI snapshot không đổi | Hi, Gradle / twice=6 |
| D | Đổi Greeter.greet(String) thành greet(String,String) | Xử lý source có ABI mới | Biên dịch lại caller và **FAILED** | Không chạy do compile fail |
| E | Đổi app call thành greet("Hello, ", "Gradle") | Thường UP-TO-DATE | Chạy do app source mới | Hello, Gradle / twice=6 |

**Không khẳng định mọi máy luôn in chính xác cùng task graph.** Task outcomes phụ thuộc việc outputs có sẵn, build cache, cấu hình Java/Gradle, annotation processors và inputs của plugins. Phép thử dùng --no-build-cache, không clean, baseline thành công và các file được sửa đúng như mô tả để làm những kết quả trên dễ quan sát.

### 7.15. Kiểm tra Java source bằng javac/java trực tiếp (tùy chọn)

Bài lab chính đo hành vi Gradle; có thể dùng JDK 17 để xác nhận code có thể compile/run **độc lập với Gradle**, ở trạng thái **A** (trước khi đổi chữ ký):

Linux/macOS:

~~~bash
mkdir -p build/manual-core build/manual-app
javac -encoding UTF-8 -d build/manual-core \
  core/src/main/java/demo/core/Prefix.java \
  core/src/main/java/demo/core/Greeter.java \
  core/src/main/java/demo/core/Calculator.java
javac -encoding UTF-8 -cp build/manual-core \
  -d build/manual-app \
  app/src/main/java/demo/app/Main.java
java -cp "build/manual-core:build/manual-app" demo.app.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build\manual-core, build\manual-app | Out-Null
javac -encoding UTF-8 -d build\manual-core core\src\main\java\demo\core\Prefix.java core\src\main\java\demo\core\Greeter.java core\src\main\java\demo\core\Calculator.java
javac -encoding UTF-8 -cp build\manual-core -d build\manual-app app\src\main\java\demo\app\Main.java
java -cp "build\manual-core;build\manual-app" demo.app.Main
~~~

**Stdout ở trạng thái A:**

~~~text
Hello, Gradle
twice=6
~~~

**Quan trọng:** Các lệnh javac thủ công **không đo incremental compilation của Gradle**; chúng chỉ xác nhận Java sources/classpath logic. Sau khi làm bước D/E, cần dùng Main.java tương ứng với chữ ký Greeter hiện tại rồi biên dịch lại bằng lệnh thích hợp.

## 8. Annotation processors: đầu vào đặc biệt của compiler

Java compiler có thể chạy **annotation processors** để sinh mã hoặc phân tích source. Processor implementation có thể phản ứng với nội dung method bodies, annotations và source code — nhiều thứ nằm ngoài ABI thuần của dependency.

Gradle cần xử lý **annotation processor classpath** như một loại input nhạy với implementation, không thể chỉ so sánh ABI giống compile classpath thông thường.

### 8.1. Khai báo đúng cấu hình

Trong Java project:

~~~groovy
dependencies {
    // Type/annotations mà source Java cần thấy khi compile.
    compileOnly 'com.example:annotations:1.0'

    // Processor chạy bằng javac; không phải app runtime dependency.
    annotationProcessor 'com.example:processor:1.0'
}
~~~

Các module com.example chỉ minh họa DSL, không phải tọa độ đã được xác nhận có trên Maven Central. Khi dùng thư viện thật như Lombok, MapStruct hay Dagger, tham khảo hướng dẫn chính xác của phiên bản đó và khai báo API/processor ở configurations phù hợp.

**Không gộp processor vào implementation chỉ để compiler “tìm thấy mọi thứ”**. Cách ấy có thể làm compile classpath nhiễu và giảm khả năng compile avoidance. Gradle Java Plugin hiện đại yêu cầu processor được khai báo rõ trên annotationProcessor path khi cần dùng; đừng kỳ vọng processor tự động chạy chỉ vì JAR nằm trong compile classpath.

### 8.2. Incremental annotation processing có điều kiện

Các annotation processors có thể hỗ trợ những chiến lược incremental như **isolating** hoặc **aggregating** nếu khai báo metadata/hành vi theo Gradle contract. Mức độ recompilation tùy processor:
- **Isolating:** output gắn chặt với những element inputs cụ thể; có khả năng giới hạn phạm vi.
- **Aggregating:** output phụ thuộc một tập elements rộng hơn; thay đổi một source có thể tác động nhiều generated outputs.
- **Non-incremental processor:** có thể buộc compile rộng hơn.

**Không khẳng định “cứ có annotationProcessor thì incremental compilation bị tắt hoàn toàn”.** Gradle có hỗ trợ processors incremental, nhưng phải có implementation và metadata tương thích. Hãy kiểm tra release notes/tài liệu của processor thực tế.

### 8.3. Thay processor có thể làm compile lại dù ABI dependencies không đổi

Ngay cả khi một library trên compileClasspath chỉ đổi method body và ABI giữ nguyên, **thay code trong JAR của annotation processor** có thể thay generated Java files. Vì vậy Gradle phải coi processor implementation classpath là input nhạy hơn so với Java compile classpath chuẩn.

Đây là lý do báo cáo compile avoidance không thể chỉ xem classpaths của application libraries mà bỏ qua processor path.

### 8.4. Generated sources và task dependencies

Nếu Gradle task tự tạo .java trước compileJava, cần nối output của producer đúng mô hình Provider/task output, đưa generated folder vào source set/compile task hợp lý. Không trỏ thẳng một build/generated/ folder bằng string path rồi coi Gradle luôn tự biết producer task phải chạy.

Generated sources thay đổi có thể khiến compiler recompile những class phụ thuộc, ngay cả khi source thủ công không đổi.

## 9. Resource changes có ảnh hưởng compile avoidance không?

Source files và resources thường thuộc những tasks khác nhau:
- **compileJava** xử lý .java thành .class.
- **processResources** copy/process files từ src/main/resources theo plugin.
- **classes** phụ thuộc các outputs compilation/resources.
- **jar** đóng gói compiled classes và resources.
- **run** dùng runtime classpath chứa classes/resources của app cùng dependencies.

Nếu đổi file properties, JSON, YAML hoặc template trong **src/main/resources** của :core, điều đó có thể:
- Làm processResources hoặc jar bị out-of-date.
- Đổi runtime behavior của app.
- Không làm Java compile ABI của core thay đổi, nên :app:compileJava có thể vẫn UP-TO-DATE.

**Nhưng có ngoại lệ:** Một annotation processor hoặc code generator đọc resource file làm input thì resource đó **có thể ảnh hưởng output Java**. Tương tự, custom task không khai báo inputs đúng có thể cho kết quả sai; phải xét cách plugin mô hình hóa thực tế.

### 9.1. Ví dụ runtime resource

Nếu Greeter tải text từ một properties file thay vì hardcode Prefix.text, thay đổi properties có thể đổi output runtime mà không làm chữ ký Greeter.greet(String) đổi. Đó vẫn là behavior change, không phải ABI change. Khi phân phối library, file resource mới cần đi cùng binary/runtime artifact.

**Kết luận:** Đừng yêu cầu recompile Java consumer chỉ vì file resources của một dependency đổi, trừ khi có quy tắc compiler/generator cụ thể cần nó.

## 10. Build cache và compile avoidance: có thể cùng hưởng lợi

Gradle build cache sử dụng fingerprints của task inputs, task implementation và outputs tương ứng để khôi phục kết quả đã tính trước đó.

Giả sử:
1. CI đã compile :app với một version của :core.
2. Developer thay chỉ method body trong :core, khiến core .class bytes đổi nhưng ABI không đổi.
3. Gradle normalization cho Java compile classpath có thể coi ABI của :core tương đương.

Khi :app:compileJava không cần thực thi lại, nó có thể UP-TO-DATE nếu outputs cũ còn. Nếu output chưa có nhưng build cache chứa một kết quả hợp lệ với cache key tương thích, Gradle có thể dùng **FROM-CACHE**. Đây là hai outcome khác nhau với mục tiêu chung: không gọi compiler của consumer khi không cần.

### 10.1. Không đọc FROM-CACHE thành incremental compiler

~~~text
> Task :app:compileJava FROM-CACHE
~~~

nghĩa là Gradle **khôi phục outputs**. Không có nghĩa Java incremental compiler vừa biên dịch 10% sources. Nếu muốn đo incremental compilation, dùng một lượt task thực thi thật và xem logs chi tiết; hạn chế cache làm nhiễu bằng --no-build-cache trong phép thử.

### 10.2. Task inputs/outputs phải đáng tin

Một custom generator không khai báo input source/template/version chính xác có thể trả cache result sai hoặc UP-TO-DATE khi thực tế output cần đổi. Không “tối ưu” build bằng cách xóa inputs khỏi task; cách đúng là mô hình hóa inputs/outputs chuẩn.

Compile avoidance dựa vào một số đặc thù của JavaCompile và compile classpath normalization; bạn **không thể** giả định mọi custom task dùng JAR đều có logic ABI tương tự JavaCompile.

### 10.3. Configuration cache không thay thế JavaCompile analysis

Nếu thấy:

~~~text
Reusing configuration cache.
~~~

đó là thông tin về **configuration phase**. JavaCompile có thể vẫn chạy, UP-TO-DATE hoặc FROM-CACHE tùy state khác. Không lấy dòng này làm chứng cứ compile avoidance đã áp dụng.

## 11. Những lý do khiến consumer compileJava vẫn chạy lại

### 11.1. API/ABI thực sự đổi

- Public method signature đổi.
- Generic/API type/visibility thay đổi.
- Public constant compile-time thay giá trị.
- Superclass/interface/module exports đổi.
- Library publication chứa API dependency mới hoặc thay phiên bản ảnh hưởng compileClasspath.

**Cách xử lý:** Đây có thể là recompilation **đúng và cần thiết**. Đừng tắt compile avoidance hoặc force UP-TO-DATE để che thay đổi API; hãy sửa code hoặc thiết kế boundary.

### 11.2. Consumer source thay đổi

Nếu app/Main.java được sửa, :app:compileJava có lý do chạy ngay cả khi :core ABI không đổi. Incremental compilation có thể thu hẹp tập sources bên trong app, nhưng không thể đặt kỳ vọng toàn bộ task UP-TO-DATE nếu source đầu vào đã đổi.

### 11.3. Compiler options hoặc toolchain đổi

Đổi Java toolchain 17 → 21, options.release, compilerArgs, debug info, annotationProcessor path hoặc JVM compilation settings có thể ảnh hưởng bytecode và vô hiệu hóa state cũ.

**Mẹo:** Cố định Gradle Wrapper/Java toolchain, tránh một máy dùng JDK lẫn lộn rồi so sánh task outcomes như thể mọi inputs giống nhau.

### 11.4. Dependency scope bị lộ quá rộng

Trong :service chỉ dùng codec nội bộ nhưng khai báo **api** thay vì **implementation**, :app compileClasspath có thể nhận thêm codec, tạo nhiều cơ hội invalidation hơn.

**Cách xử lý:** Dùng java-library và chuyển đúng internal dependencies sang implementation, chỉ giữ api khi public contract cần type của dependency.

### 11.5. Annotation processor thay đổi

Processor có thể đọc nhiều source/metadata hơn public ABI, hoặc processor không hỗ trợ incremental mode. Kiểm tra:
- annotationProcessor configuration,
- Gradle --info logs,
- processor version/metadata,
- generated sources và task wiring.

Không chuyển processor sang compileOnly nếu mã cần chạy processor; cần scope đúng chứ không tắt công việc cần thiết.

### 11.6. Một custom task can thiệp outputs

Custom build script có thể xóa build/classes, ghi trực tiếp vào output của compileJava, đọc source/generated files mà không khai báo dependency, hoặc luôn chạy tasks.dependsOn logic với input thay đổi. Kết quả là up-to-date checks kém ổn định.

**Cách xử lý:** Dùng Provider API, task output properties và dependencies rõ ràng, tránh nhiều tasks cùng ghi một output folder.

### 11.7. Trùng class hoặc classpath không ổn định

Nếu fileTree(dir: 'libs', include: ['*.jar']) nhận JAR mới, classpath có thể đổi. Nếu hai JAR chứa cùng class, resolution/version conflict không tự quyết định như với external module metadata. Build có thể compile against một class khác trong classpath order, gây lỗi runtime.

Giữ classpath có version và metadata nhất quán; dùng dependencyInsight và archive inspection khi cần.

### 11.8. Chạy clean, --rerun-tasks hoặc đổi môi trường

Đây thường là **yếu tố thử nghiệm**, không phải compile avoidance “bị lỗi”. Xác minh không có flags làm task luôn chạy, không thay Gradle/JDK/project path, và giữ outputs/state qua các lượt đo.

## 12. Quan sát thay đổi tại class và API boundary

### 12.1. Xem public API bằng javap

Sau khi build core:

~~~bash
./gradlew :core:classes
javap -public -classpath core/build/classes/java/main demo.core.Greeter
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat :core:classes
javap -public -classpath core\build\classes\java\main demo.core.Greeter
~~~

Ở trạng thái baseline, một public method đáng chú ý:

~~~text
public static java.lang.String greet(java.lang.String);
~~~

Sau khi đổi API ở bước D:

~~~text
public static java.lang.String greet(java.lang.String, java.lang.String);
~~~

**javap output thật** có thể thêm version, header, constructors hoặc các dòng khác. Hai signatures ở trên là phần cần so sánh. Với private Prefix, nó không xuất hiện trong public API của Greeter; dùng javap -c nếu cần xem bytecode method bodies nhưng đừng đồng nhất disassembly với Gradle ABI fingerprint.

### 12.2. Vẽ ranh giới producer–consumer

~~~text
Before:
  :core Prefix.text(): "Hello, "    [implementation]
          |
          v
  :core Greeter.greet(String)        [public ABI giữ nguyên]
          |
          v
  :app Main.greet("Gradle")          [compile avoidance khả thi]

After body change:
  :core Prefix.text(): "Hi, "       [implementation đổi]
          |
          v
  :core Greeter.greet(String)        [public ABI vẫn thế]
          |
          v
  :app compileJava UP-TO-DATE?      [thường có, nếu inputs khác không đổi]

After API change:
  :core Greeter.greet(String,String) [public ABI đổi]
          |
          v
  :app Main.greet("Gradle")          [source không còn tương thích]
          |
          v
  :app compileJava FAILED           [cần sửa caller]
~~~

Dấu hỏi ở trạng thái UP-TO-DATE nhắc rằng build environment và các inputs khác vẫn quyết định outcome cuối. **Không hứa một thao tác duy nhất luôn cho cùng hiệu năng trên mọi version Gradle**.

### 12.3. Lệnh xem dependency boundary

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Ở lab, app compileClasspath có project :core; app runtimeClasspath cũng có :core. Với mô hình java-library có external api/implementation dependencies, hai reports có thể khác nhau rõ rệt.

Nhớ rằng dependencies report mô tả **resolved dependency graph**, không tự chứng minh JavaCompile task đã recompile những source nào.

## 13. Nguyên tắc thiết kế API để build nhanh mà vẫn đúng

### 13.1. Ưu tiên API nhỏ, ổn định

Nếu module library expose quá nhiều class/field/method không cần thiết, thay đổi “vô tình public” dễ làm ABI đổi và downstream compilation bị ảnh hưởng.

Nên:
- Expose tối thiểu types/methods cần cho consumer.
- Giữ implementation classes package-private/private khi phù hợp.
- Dùng interface/contract ổn định để ngăn chi tiết codec/DB/library lọt vào API.
- Dùng java-library để phân biệt api và implementation.
- Đọc Javadoc/public API docs trong code review, không chỉ xem functionality.

### 13.2. Không tối ưu bằng cách giấu API cần thiết

Nếu public API thật sự trả một type từ dependency ngoài, khai báo implementation thay api có thể khiến consumer compile thất bại. **Đúng đắn và khả năng dùng API quan trọng hơn một lần recompilation.** Phạm vi dependency phải phản ánh hợp đồng thực tế.

### 13.3. Dùng accessor cho những giá trị có thể đổi

Tránh public compile-time constants cho giá trị thường thay đổi hoặc cần runtime configuration. Nếu cần giá trị thay đổi behavior mà không bắt consumer recompile, method getter hoặc configuration runtime có thể hợp lý hơn.

### 13.4. Tách resource/runtime behavior khỏi compile boundary

Một file message template, localization hoặc feature flag thay đổi thường chỉ cần runtime update, không phải đổi chữ ký Java. Cấu trúc module hợp lý giúp tránh recompilation không cần thiết, nhưng vẫn phải test runtime behavior.

### 13.5. Đừng phá API chỉ để “kích hoạt compiler”

Không thêm dummy public method hoặc đổi method signature chỉ để buộc downstream compileJava chạy. Nếu build cần test integration, hãy gọi test/run task phù hợp; nếu có generated outputs, khai báo task inputs/outputs đúng. Thay đổi API giả tạo gây breaking changes và không sửa nguyên nhân gốc.

## 14. Troubleshooting theo triệu chứng

### Lỗi 1 — Sửa private method mà :app:compileJava vẫn chạy

**Nguyên nhân có thể:** :app source/compile options/toolchain đã đổi; build bị clean/rerun; annotation processor path đổi; compile classpath bị lộ implementation dependencies; task outputs bị xóa hoặc cache behavior khác.

**Cách xử lý:** So sánh :app:compileJava inputs, đọc --info logs, bỏ --rerun-tasks/clean, kiểm tra dependency graph và build state. Đừng khẳng định Gradle sai chỉ từ một task outcome.

### Lỗi 2 — Sửa method body nhưng app runtime không thấy behavior mới

**Nguyên nhân có thể:** App đang chạy binary JAR cũ, dùng dependency ngoài đã publish thay project(':core'), classpath có JAR trùng, launcher riêng chưa cập nhật hoặc JavaExec dùng classpath khác.

**Cách xử lý:** Xem :app:dependencies --configuration runtimeClasspath, project dependency và actual artifact loaded, kiểm tra classpath của run. **Compile avoidance không đồng nghĩa runtime classes không được cập nhật**.

### Lỗi 3 — Chuyển implementation thành api rồi compile cả chuỗi dự án

**Nguyên nhân:** Consumer compileClasspath nhận dependencies mới và ABI/classpath snapshot thay đổi.

**Cách xử lý:** Chỉ expose api dependencies khi public contract cần chúng; giữ implementation cho internal libraries, review Gradle Module Metadata và dependencies reports.

### Lỗi 4 — Đổi public method signature nhưng Gradle không báo lỗi ngay

**Nguyên nhân có thể:** Task của consumer không được chạy, source cũ không gọi method đó, consumer chưa resolve project/library mới, hoặc build process dùng cached compiled binary khác.

**Cách xử lý:** Chạy đúng :consumer:compileJava, xác định dependency project/version, dùng javap -public và compileClasspath. Không giả định mọi consumer sẽ fail khi public method chỉ thêm overload.

### Lỗi 5 — NoSuchMethodError khi JVM chạy nhưng source build từng thành công

**Nguyên nhân:** Runtime classpath có version khác với classpath mà app đã compile, hoặc public API library đổi mà consumer bytecode chưa được rebuild.

**Cách xử lý:** So sánh runtimeClasspath vs compileClasspath, kiểm tra versions và module variants, tránh dùng file JAR cũ hoặc force downgrade không tương thích. Đây là vấn đề binary compatibility, khác việc compiler có chạy ở lượt build mới không.

### Lỗi 6 — Đổi public static final constant nhưng output vẫn là giá trị cũ

**Nguyên nhân:** Constant có thể đã được javac inline trong consumer bytecode.

**Cách xử lý:** Đảm bảo consumer được compile lại với version library mới và Gradle thấy constant value change; cân nhắc accessor thay field constant nếu value có thể thay đổi.

### Lỗi 7 — Processor làm full recompilation

**Nguyên nhân:** Processor không incremental/không khai báo metadata đúng, processor path thay đổi hoặc generated files có quan hệ rộng.

**Cách xử lý:** Xem processor documentation và --info, khai báo annotationProcessor đúng, kiểm tra isolating/aggregating support, thử upgrade processor và tách scopes.

### Lỗi 8 — Task báo FROM-CACHE nhưng người dùng nghĩ incremental compiler chạy

**Nguyên nhân:** Build cache trả output từ lần khác.

**Cách xử lý:** Hiểu FROM-CACHE khác UP-TO-DATE/EXECUTED. Khi thử nguyên lý incremental compilation, dùng --no-build-cache và chạy nhiều lượt không clean.

### Lỗi 9 — Task báo NO-SOURCE trong Java project

**Nguyên nhân:** Source files không ở sourceSet/path mong đợi hoặc sourceSet tương ứng không có Java files.

**Cách xử lý:** Kiểm tra src/main/java, src/test/java, sourceSets configuration, plugin Java và project path. NO-SOURCE không phải compile avoidance.

### Lỗi 10 — Thêm resource khiến JAR được build lại nhưng app compiler không chạy

**Nguyên nhân:** Resources ảnh hưởng processResources/jar/runtime artifact, không bắt buộc làm compiled ABI đổi.

**Cách xử lý:** Đây thường là hành vi đúng; test runtime/package contents thay vì cố ép compileJava chạy.

### Lỗi 11 — Đổi JDK17 sang JDK khác làm nhiều tasks out-of-date

**Nguyên nhân:** Java toolchain/compiler options là compile inputs, có thể tạo bytecode khác.

**Cách xử lý:** Pin toolchain và Gradle Wrapper, review compatibility, hạn chế so kết quả performance giữa hai môi trường không tương đương.

### Lỗi 12 — Một module dùng java thay vì java-library và dependency rò ra consumer

**Nguyên nhân:** Java Plugin không có API/implementation separation rõ như Java Library Plugin; Gradle có thể expose dependencies qua metadata/variants theo plugin model.

**Cách xử lý:** Với library reusable, dùng java-library và khai báo api/implementation chính xác. Không trông chờ Gradle suy ra hợp đồng API từ source bằng cách tự phân loại dependency dù bạn chưa khai báo.

### Lỗi 13 — Custom task ghi vào build/classes/java/main trực tiếp

**Nguyên nhân:** Nhiều producers ghi cùng thư mục output làm Gradle khó kiểm tra chính xác inputs/outputs, phá cache và task dependency modeling.

**Cách xử lý:** Mỗi task nên có output riêng, kết nối qua Provider và source set/classpath phù hợp; không tự sửa file .class sau compile mà không khai báo bước transform.

### Lỗi 14 — Có configuration cache nhưng compileJava vẫn chạy

**Nguyên nhân:** Configuration cache chỉ tái sử dụng **mô hình configuration/task graph**; task compilation vẫn dựa vào inputs, ABI và outputs.

**Cách xử lý:** Phân tích task outcomes và classpath snapshots riêng, không lấy trạng thái configuration cache làm dấu hiệu compiler avoidance.

### Lỗi 15 — Incremental compiler biên dịch nhiều file hơn dự tính

**Nguyên nhân:** Dependency graph giữa classes, constant usage, generated files hoặc processor có phạm vi rộng; Gradle có thể chọn recompile an toàn hơn.

**Cách xử lý:** Dùng --info và công cụ chẩn đoán phù hợp, xác định ABI change thật sự, tối ưu module boundaries/processors. Không kỳ vọng file count cố định cho mọi build.

## 15. Quy trình đo hiệu năng Gradle đáng tin

Một bài benchmark nhỏ dễ bị sai bởi cache, daemon warm-up, I/O, JDK khác và số lượng class ít. Để kết luận compile avoidance thực sự giúp bao nhiêu thời gian:

1. Dùng cùng Gradle Wrapper, JDK/toolchain và các plugin versions.
2. Build baseline thành công; lưu logs và task outcomes.
3. Chạy lại không thay đổi để xác nhận UP-TO-DATE behavior.
4. Sửa **duy nhất một method body** trong dependency producer.
5. Chạy consumer compileJava với --console=plain --info --no-build-cache.
6. Ghi nhận producer JavaCompile executed/incremental và consumer JavaCompile UP-TO-DATE hay không.
7. Hoàn tác, sửa **duy nhất một public API signature** rồi chạy lại.
8. Ghi nhận ABI change và những consumers thực sự phải compile.
9. Lặp vài lần với nguồn đủ lớn, không chỉ đánh giá một lần chạy có JIT/OS cache biến động.
10. Khi cần khảo sát lớn hơn, dùng **Gradle Build Scan/Develocity** (nếu khả dụng và được phép gửi metadata) để xem task performance và cause of invalidation.
11. Tách timing configuration phase, dependency resolution, code generation, JavaCompile và packaging.
12. Tránh suy rộng kết quả của một Java-only project sang Kotlin/Android/Groovy builds.

**Quan trọng:** Trong bài lab nhỏ, lợi ích tính bằng mili-giây có thể bị startup overhead che khuất. Điều cần học là **đúng cơ chế và đúng outcome**, không phải một con số tốc độ được bịa ra.

## 16. Checklist review thay đổi source hoặc dependency

| Câu hỏi | Nên kiểm tra |
|---|---|
| Có đổi public/protected signatures không? | javap, source diff, API binary compatibility checker |
| Có đổi compile-time constants không? | Public static final fields/consumer usage |
| Có đổi API exposure qua api/implementation không? | :consumer:dependencies --configuration compileClasspath |
| Mã chỉ đổi method body/private implementation? | Gradle JavaCompile task outcomes, ABI snapshot behavior |
| Có processor/generator mới không? | annotationProcessor path và incremental metadata |
| Source/resources thuộc task nào? | compileJava, processResources, jar, run |
| Output core mới đã được dùng lúc run chưa? | Runtime classpath, actual project dependency |
| Có build cache làm nhiễu không? | UP-TO-DATE vs FROM-CACHE, --no-build-cache |
| Có clean/--rerun-tasks trong phép thử không? | Loại bỏ flags ảnh hưởng up-to-date |
| Compiler/JDK/Gradle có đổi không? | Wrapper, toolchain và compiler arguments |
| CI có test behavior thay đổi không? | Unit/integration tests, không chỉ compile |
| Consumer cũ đã compile được với public API mới chưa? | Source compatibility và ABI compatibility tests |
| Có JAR trùng class hoặc fileTree không kiểm soát? | Runtime/compile classpath và JAR inspection |
| Generated outputs có producer wiring đúng không? | Task outputs/Provider/sourceSets |
| Tooling ngoài Java Plugin được kiểm chứng chưa? | Kotlin/Groovy/AGP-specific incremental model |

## 17. Bài tập thực hành

**Bài 1.** :core thay return "Hello" thành return "Hi" trong method body của public greet(String). App không sửa source. :app:compileJava có nhất thiết phải chạy lại không?

**Bài 2.** Vì sao :core:compileJava có thể chạy nhưng :app:compileJava UP-TO-DATE sau cùng một thay đổi?

**Bài 3.** Khác nhau giữa **compile avoidance** và **incremental Java compilation** là gì?

**Bài 4.** Gradle in :app:compileJava FROM-CACHE. Có thể kết luận Java incremental compiler đã chạy cục bộ không?

**Bài 5.** Xóa :core:Greeter.greet(String) và chỉ còn greet(String,String). App cũ gọi greet("Lan"). Kết quả compile hợp lý là gì?

**Bài 6.** Vì sao sửa comment trong Java source vẫn có thể khiến JavaCompile của producer được xem xét chạy, dù downstream compiler không cần chạy?

**Bài 7.** Một library có external codec được dùng nội bộ, public API chỉ trả String. Nên khai báo dependency codec là api hay implementation để giảm consumer compile classpath?

**Bài 8.** Nếu public method trả com.example.contracts.Result từ dependency contracts, nên khai báo contracts thế nào trong java-library?

**Bài 9.** Đổi một public static final int VERSION=1 thành VERSION=2; vì sao consumer có thể cần recompile dù field type/name không đổi?

**Bài 10.** App.run in output mới mặc dù app.compileJava UP-TO-DATE. Vì sao không mâu thuẫn?

**Bài 11.** Processor code thay đổi nhưng library API/ABI không đổi. Có thể compiler vẫn cần chạy lại không? Vì sao?

**Bài 12.** Một custom task thay đổi resources rồi Jar task chạy lại. Có nhất thiết app JavaCompile phải chạy không?

**Bài 13.** Chạy ./gradlew clean --no-build-cache :app:compileJava để đo compile avoidance giữa hai lượt thay đổi. Phương pháp này có nhược điểm gì?

**Bài 14.** Khi Gradle chọn file classes output từ project dependency thay vì JAR, compiler downstream có vẫn có thể tận dụng classpath ABI normalization không?

**Bài 15.** :app dùng java-library library :service với implementation project(':codec'). Khi :codec đổi internal method body, app compileClasspath có phải luôn chứa :codec không?

**Bài 16.** Một module Java đổi toolchain từ 17 lên 21. Vì sao khó dùng kết quả này để đánh giá compile avoidance khi method body đổi?

**Bài 17.** Thay đổi public generic signature nhưng erased descriptor có thể tương tự. Có nên luôn coi đó là implementation-only change không?

**Bài 18.** Phân biệt source compatibility, binary compatibility và behavioral compatibility bằng một ví dụ đổi API hoặc logic.

**Bài 19.** Khi thấy task NO-SOURCE hoặc SKIPPED, có được ghi “compile avoidance đã được xác nhận” không?

**Bài 20.** Đề xuất một checklist 5 bước chứng minh một cải tiến compile avoidance bằng Gradle --info và không dùng cache.

### Gợi ý đáp án

1. **Không nhất thiết.** Nếu ABI unchanged, Gradle có thể tránh downstream compilation.
2. Producer source đổi nên task có việc; consumer chỉ nhìn ABI của dependency compile classpath, nên có thể không cần compiler.
3. **Compile avoidance** có thể bỏ qua cả downstream JavaCompile task; **incremental Java compilation** chỉ biên dịch những sources bị ảnh hưởng **khi task phải chạy**.
4. **Không.** FROM-CACHE nghĩa là lấy outputs có sẵn từ cache.
5. **Compile error** vì method một tham số không còn; đây là ABI breaking change.
6. Source input của producer đổi, nên producer task có thể xử lý; Javadoc/comment thường không làm compiled public ABI đổi, downstream có thể UP-TO-DATE.
7. **implementation** nếu không expose codec types trong API.
8. **api** nếu Result thật sự nằm trong public contract consumer cần để compile.
9. Java compiler có thể inline compile-time constants trong bytecode caller; thay giá trị có thể đòi recompile.
10. Runtime classes mới của core được dùng khi app chạy; Main.class cũ vẫn gọi một public method signature hợp lệ.
11. **Có.** Processor implementation ảnh hưởng generated code, được Gradle xem là input nhạy hơn ABI.
12. **Không.** Resources thường ảnh hưởng processResources/jar/runtime, không nhất thiết compile ABI.
13. clean xóa outputs/state; task phải xử lý nhiều hơn, che khả năng UP-TO-DATE. Dùng baseline thành công và giữ build outputs để đo.
14. **Có thể**, nếu Gradle JavaCompile xử lý đúng classpath snapshots/normalization của producer outputs và không có yếu tố khác.
15. **Không** theo compile variant chuẩn của java-library; implementation dependencies không tự leak vào consumer compileClasspath.
16. JDK/toolchain/bytecode là compiler inputs khác; phép thử không cô lập một method-body change.
17. **Không.** Generic/public API metadata có thể ảnh hưởng Java compiler và Gradle ABI extraction.
18. Ví dụ xóa method: source consumer fail (source incompatibility), bytecode cũ có thể NoSuchMethodError (binary incompatibility); đổi thân method giữ signature nhưng đổi kết quả có thể behavioral incompatibility.
19. **Không.** NO-SOURCE nói không có source; SKIPPED có thể do điều kiện task, không nhất thiết do ABI.
20. Giữ cố định Gradle/JDK, build baseline, chạy lại không đổi, sửa một body method, xem :core/:app:compileJava outcomes bằng --info --no-build-cache; đối chiếu với lần đổi public API signature.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — The Java Plugin, Compilation Avoidance](https://docs.gradle.org/current/userguide/java_plugin.html): Java compile avoidance, những thay đổi ABI-compatible, annotation processor classpath.
- [Gradle User Manual — Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html): incremental Java compilation mặc định và compile avoidance trong các phiên bản Gradle.
- [Gradle User Manual — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs, up-to-date checks, snapshot/fingerprint và task validation.
- [Gradle User Manual — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): compile classpath ABI normalization và cách tái sử dụng kết quả JavaCompile.
- [Gradle User Manual — Caching Java Projects](https://docs.gradle.org/current/userguide/caching_java_projects.html): compile avoidance, annotation processors và interaction với build cache.
- [Gradle User Manual — Gradle Optimizations](https://docs.gradle.org/current/userguide/gradle_optimizations.html): UP-TO-DATE/FROM-CACHE/NO-SOURCE task outcomes.
- [Gradle User Manual — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation, ABI boundary, consumer compile/runtime classpaths.
- [Gradle User Manual — Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): compiler options, toolchains và JavaCompile tasks.
- [Gradle DSL — CompileOptions](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html): options.incremental, encoding, compilerArguments và annotation processing.
- [Gradle User Manual — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): kiểm tra compileClasspath/runtimeClasspath và dependencyInsight khi cần.
- [Oracle JDK 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): Java compiler, classpath, source/bytecode và options.

**Ghi nhớ:** **Incremental Java compilation** giảm số source files compiler phải biên dịch **khi JavaCompile chạy**. **Compile avoidance** dùng ABI của compile classpath để có thể **bỏ qua cả JavaCompile của consumer** sau implementation-only changes. **java-library api/implementation** giữ compile API boundary rõ ràng, giúp tránh invalidation dây chuyền. **UP-TO-DATE** khác **FROM-CACHE** và khác incremental compilation. Đo đúng project, đúng compiler inputs, đúng task outcomes và luôn kiểm thử runtime behavior sau thay đổi.