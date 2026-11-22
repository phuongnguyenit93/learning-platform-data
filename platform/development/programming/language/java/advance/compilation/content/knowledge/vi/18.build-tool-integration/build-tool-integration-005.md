# Biên dịch tăng dần, phụ thuộc thay đổi và khi nào cần build sạch trong Java

## 1. Mục tiêu và bối cảnh

Trong dự án Java, mỗi lần sửa một dòng mã nguồn không nhất thiết phải xóa toàn bộ sản phẩm biên dịch rồi chạy lại mọi tác vụ. Công cụ build có thể xác định phần nào thực sự bị ảnh hưởng, bỏ qua những tác vụ có đầu vào không đổi hoặc chỉ biên dịch lại lớp cần thiết. Hiểu cơ chế này giúp rút ngắn thời gian phát triển, xử lý lỗi “chạy vẫn ra mã cũ” và thiết kế pipeline CI đáng tin cậy.

Sau bài học, bạn cần phân biệt được:

- **Incremental build:** bỏ qua tác vụ có đầu vào/đầu ra còn hợp lệ và chỉ xử lý phần bị thay đổi.
- **Incremental compilation:** trong một tác vụ biên dịch, chỉ biên dịch lại tập nguồn chịu ảnh hưởng khi trình biên dịch/công cụ build hỗ trợ.
- **Compilation avoidance:** bỏ qua biên dịch của module phụ thuộc khi API/ABI của thư viện đầu vào không đổi.
- **Build cache:** tái sử dụng đầu ra từng được tạo với đầu vào tương đương; cache không đồng nghĩa với việc chỉ biên dịch vài tệp.
- **Clean build:** xóa đầu ra do build quản lý rồi tạo lại; hữu ích để loại bỏ trạng thái cũ nhưng tốn thời gian và không sửa được cấu hình sai.

Các tối ưu này có thể phối hợp nhưng có phạm vi khác nhau. Kết luận “đã sửa file nên mọi module phải compile lại” và kết luận “build thành công nên mọi class đều mới” đều có thể sai.

## 2. Mô hình: điều gì làm một kết quả biên dịch hết hiệu lực?

Một bản build có thể xem như chuỗi chuyển đổi:

```text
Java source + generated source + compile classpath
       + compiler/JDK + options + annotation processors
                           |
                           v
                     JavaCompile
                           |
                           v
                    *.class / outputs
                           |
                           v
                  jar / tests / packaging
```

Để biết có cần chạy lại công việc hay không, công cụ build so sánh **đầu vào đã khai báo**, trạng thái đầu ra và quy tắc phụ thuộc. Những đầu vào quan trọng có thể gồm:

1. Tệp nguồn Java được thêm, sửa hoặc xóa.
2. Tệp `.class` hoặc JAR trên **compile classpath** và bề mặt API/ABI được tiêu thụ.
3. Phiên bản JDK/toolchain, các tùy chọn `--release`, `-parameters`, warning flags hoặc cấu hình biên dịch có ảnh hưởng đến bytecode.
4. Annotation processors, cấu hình và tài nguyên chúng đọc; mã được sinh trong quá trình build.
5. Đầu ra bị mất, thay đổi ngoài build hoặc bị tác vụ khác ghi đè.
6. Quan hệ giữa các task/module; ví dụ, `:app:compileJava` cần sản phẩm đúng của `:lib:compileJava`.

Một hệ thống chỉ kiểm tra “ngày sửa file .java có mới hơn .class không?” sẽ bỏ sót trường hợp phương thức công khai đổi chữ ký nhưng một file gọi nó không đổi. Một hệ thống đáng tin cần theo dõi phụ thuộc và làm mất hiệu lực đúng đầu ra chịu ảnh hưởng.

**Hai cấp độ phụ thuộc phải tách riêng:**

- **Phụ thuộc nguồn/lớp:** `OrderService` gọi `Pricing.calculate()`; thay đổi chữ ký `calculate` có thể khiến `OrderService` cần được biên dịch lại.
- **Phụ thuộc task/module:** `:app:compileJava` lấy lớp từ `:core`; task của app có thể không cần chạy khi thư viện chỉ đổi cách tính nội bộ nhưng vẫn giữ ABI.

Thông tin phụ thuộc chính xác đến đâu tùy công cụ, phiên bản, loại bộ xử lý annotation và cách cấu hình. Không phải mọi thay đổi đều chỉ biên dịch lại đúng một file.

## 3. API, ABI và phạm vi lan truyền

**API** là giao diện mà mã nguồn khác có thể dùng: lớp, phương thức, constructor, field và kiểu/khả năng truy cập phù hợp. **ABI (Application Binary Interface)** ở đây là phần giao diện trong class file ảnh hưởng đến khả năng mã đã biên dịch liên kết và tương tác với lớp đó. Gradle phân tích ABI trên compile classpath để quyết định có tránh biên dịch downstream hay không.

| Thay đổi ở thư viện | Tác động điển hình |
|---|---|
| Chỉ đổi thân một phương thức, không đổi chữ ký | Phải biên dịch phần nguồn chứa thay đổi; module tiêu thụ thường được tránh biên dịch nhờ ABI không đổi |
| Đổi tên hoặc kiểu tham số, kiểu trả về, mức truy cập công khai | ABI thay đổi; các nguồn phụ thuộc tương ứng có thể phải biên dịch lại và có thể báo lỗi |
| Thêm/xóa phương thức công khai, superclass, interface | Có thể làm thay đổi cách phân giải lời gọi hoặc hợp đồng kiểu; cần đánh giá các lớp dùng API |
| Đổi `private` implementation | Thường không ảnh hưởng ABI của module tiêu thụ |
| Đổi giá trị `public static final int` là hằng tại thời điểm biên dịch | Có rủi ro **constant inlining** trong class đã biên dịch; phải bảo đảm mã tiêu thụ được làm mới đúng |
| Thay đổi annotation hoặc metadata mà processor sử dụng | Có thể cần tái sinh mã hay biên dịch phạm vi rộng hơn, kể cả khi chữ ký Java thông thường không đổi |
| Thay đổi dependency/compiler flag | Có thể làm mất hiệu lực task; phạm vi phụ thuộc khả năng theo dõi của công cụ |
| Xóa/đổi tên lớp | Phải loại bỏ đầu ra cũ và làm mới các lớp tham chiếu; nếu giữ class cũ, có thể xuất hiện hành vi “ma” |

Đừng nhầm “ABI không đổi” với “ứng dụng chạy giống hệt”. Ví dụ sửa phép tính trong một phương thức sẽ thay đổi kết quả runtime mặc dù module gọi nó không phải biên dịch lại. Module đó khi chạy sẽ nạp implementation mới từ classpath.

**Hằng compile-time là ngoại lệ cần chú ý.** Với khai báo:

```java
package example.api;

public final class Limits {
    private Limits() {}

    public static final int MAX_RETRIES = 3;
}
```

Một lớp khác dùng `Limits.MAX_RETRIES` có thể được `javac` chép trực tiếp giá trị `3` vào bytecode. Nếu sửa thành `5` mà chỉ biên dịch lại `Limits.class`, bytecode consumer cũ vẫn có thể giữ `3`. Đây là lý do bộ theo dõi biên dịch phải hiểu phụ thuộc hằng; không nên tự biên dịch thủ công từng file một cách tùy tiện.

## 4. Ví dụ Java 17+: vì sao phải biên dịch lại lớp phụ thuộc?

Tạo cây thư mục:

```text
src/
└── main/
    └── java/
        └── example/
            ├── api/
            │   └── Price.java
            └── app/
                └── Main.java
```

**Tệp `src/main/java/example/api/Price.java`:**

```java
package example.api;

public final class Price {
    private Price() {}

    public static int total(int unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

**Tệp `src/main/java/example/app/Main.java`:**

```java
package example.app;

import example.api.Price;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Price.total(20, 3));
    }
}
```

Tạo thư mục `out` (Unix/macOS: `mkdir -p out`; PowerShell: `New-Item -ItemType Directory -Force out`) rồi chạy tại thư mục dự án:

```bash
javac -d out src/main/java/example/api/Price.java src/main/java/example/app/Main.java
java -cp out example.app.Main
```

Kết quả:

```text
60
```

Bây giờ chỉ đổi **kiểu trả về** của `Price.total` thành `long`, giữ lại các tham số và thân phương thức:

```java
public static long total(int unitPrice, int quantity) {
    return (long) unitPrice * quantity;
}
```

Sau khi sửa `Price.java`, hãy cố tình chỉ biên dịch lớp cung cấp API, trong khi `Main.class` cũ vẫn còn:

```bash
javac -cp out -d out src/main/java/example/api/Price.java
java -cp out example.app.Main
```

Lần chạy thứ hai sẽ thất bại với **`java.lang.NoSuchMethodError`** vì `Main.class` cũ còn gọi phương thức có descriptor trả về `int`, trong khi `Price.class` mới chỉ cung cấp descriptor trả về `long`. Thông điệp lỗi cụ thể có thể khác nhau giữa các phiên bản JVM, nhưng bản chất là liên kết tới chữ ký nhị phân cũ.

Biên dịch lại consumer rồi chạy:

```bash
javac -cp out -d out src/main/java/example/app/Main.java
java -cp out example.app.Main
```

Kết quả lại là:

```text
60
```

Thí nghiệm chỉ ra hai việc khác nhau: *mã nguồn thay đổi ở đâu* và *class nào cần cập nhật do phụ thuộc*. Bộ build hiện đại được thiết kế để tự tính toán quan hệ này. `javac` với lệnh biên dịch các file được chỉ định như trên không tự cung cấp một hệ thống theo dõi task/đồ thị build xuyên các lần chạy giống Gradle.

**Lưu ý:** `NoSuchMethodError`, `NoSuchFieldError` và `ClassNotFoundException` còn có thể đến từ xung đột phiên bản JAR hoặc classpath runtime; không mặc định quy mọi lỗi như vậy cho incremental compilation.

## 5. Gradle theo dõi thay đổi như thế nào?

Với Java plugin, hai cơ chế liên quan nhưng độc lập:

**(A) Task up-to-date / incremental build.** Nếu đầu vào đã khai báo và đầu ra của `:compileJava` tương ứng với lần chạy trước, Gradle có thể báo `UP-TO-DATE` và không chạy task. Nếu đầu ra hợp lệ đã có ở build cache, có thể thấy `FROM-CACHE`. Nếu task chạy, nó có thể vẫn chỉ biên dịch một tập lớp bị ảnh hưởng.

**(B) Incremental Java compilation và compile avoidance.** `JavaCompile` có thể phát hiện các lớp nguồn bị thay đổi và phụ thuộc bị ảnh hưởng. Giữa các module, Gradle có thể tránh biên dịch consumer nếu thay đổi thư viện không ảnh hưởng ABI. Cơ chế incremental compilation đã được bật mặc định trên các phiên bản Gradle hiện đại.

Một cấu hình đơn giản cho Java 17 trở lên dùng Java toolchain:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Tệp này là `build.gradle`. Lệnh chạy bằng Gradle Wrapper từ root dự án (Unix/macOS; trên Windows dùng `gradlew.bat`):

```bash
./gradlew compileJava --console=verbose
./gradlew compileJava --console=verbose
```

Sau lần build đầu thành công, lần thứ hai *thường* hiện `:compileJava UP-TO-DATE` nếu không có đầu vào/đầu ra liên quan thay đổi. Không nên diễn giải một task chạy lại là luôn “biên dịch toàn bộ”; xem `--info` để biết lý do invalidation và hoạt động biên dịch thực tế.

Ví dụ dự án nhiều module:

```text
:core  (Pricing.java)
   |
   v
:app   (OrderApplication.java dùng core)
```

- Nếu chỉ sửa thân `Pricing.calculate()`: `:core:compileJava` cần cập nhật output; `:app:compileJava` thường có thể tránh chạy vì ABI core vẫn tương thích.
- Nếu đổi một chữ ký API mà app gọi: app cần được kiểm tra và có thể phải biên dịch lại hoặc thất bại vì không còn API tương thích.
- Nếu thay đổi một nguồn không liên quan tới app, việc tái biên dịch trong module còn phụ thuộc phân tích class dependencies và các processor.

Ví dụ khai báo phụ thuộc Gradle:

```groovy
dependencies {
    implementation project(':core')
}
```

Khai báo này nằm trong `app/build.gradle` của dự án multi-project đã khai báo `:core` và `:app` trong settings. Đây là đoạn cấu hình minh họa, không phải dự án tự chạy chỉ bằng một dòng.

### 5.1. Annotation processing và mã sinh

Các công cụ như MapStruct, Lombok hoặc processor tự viết có thể sinh Java source/class từ nhiều đầu vào. Tính chính xác phụ thuộc khả năng công cụ build nhìn thấy đầy đủ đầu vào của processor.

Trong Gradle, dependency của processor nên đặt trên cấu hình riêng:

```groovy
dependencies {
    annotationProcessor 'org.example:sample-processor:1.0'
}
```

Dòng trên chỉ minh họa **vị trí cấu hình**: tọa độ `org.example:sample-processor:1.0` là ví dụ, không phải artifact để tải và chạy. Processor thực tế phải dùng tọa độ có tồn tại.

Gradle phân biệt processor **isolating** (đầu ra gắn với từng đầu vào), **aggregating** (đầu ra tổng hợp nhiều đầu vào) và processor không hỗ trợ incremental. Nếu processor không đáp ứng hợp đồng incremental, thay đổi nhỏ có thể khiến biên dịch lại rộng hơn. Khi processor đọc file YAML/JSON/resource hoặc biến môi trường mà task không khai báo làm đầu vào, kết quả “up-to-date” có thể sai. Đó là lỗi khai báo dependency/input, không phải lý do lâu dài để luôn chạy `clean`.

### 5.2. Những trạng thái dễ nhầm

| Dấu hiệu từ Gradle | Ý nghĩa thực tế |
|---|---|
| `UP-TO-DATE` | Task không chạy vì trạng thái đầu vào và đầu ra hiện tại đã hợp lệ |
| `FROM-CACHE` | Đầu ra được khôi phục từ cache phù hợp |
| Task chạy bình thường | Có thay đổi hoặc tối ưu không áp dụng; chưa thể kết luận nó đã biên dịch mọi source |
| `NO-SOURCE` | Không có nguồn đầu vào thuộc task để xử lý |
| `SKIPPED` | Task không thực thi vì điều kiện/thiết lập skip; không tương đương với việc output đã được kiểm chứng mới nhất |

Khi phân tích lỗi, kiểm tra task cụ thể (`compileJava`, `compileTestJava`, `processResources`, `jar`, task code generation) thay vì coi toàn bộ chữ “BUILD SUCCESSFUL” là bằng chứng rằng từng lớp nguồn vừa được biên dịch.

## 6. Maven: cùng mục tiêu, cách quyết định có thể khác

Maven cũng có cơ chế nhận biết thay đổi thông qua Maven Compiler Plugin và lifecycle, nhưng **không nên mặc định nó có thuật toán theo dõi ABI, compile avoidance và phạm vi recompile giống Gradle**. Tính năng phụ thuộc phiên bản plugin và cấu hình.

Với Maven Compiler Plugin 3.x, `useIncrementalCompilation=true` là mặc định của compiler javac: plugin xét thay đổi ở source và dependency JAR; khi cần, nó có thể biên dịch lại toàn bộ source của module. Tùy chọn `false` dựa nhiều hơn vào file mới hơn và có nguy cơ bỏ sót consumer khi API thay đổi. Dòng Maven Compiler Plugin 4.x có lựa chọn chiến lược `incrementalCompilation` chi tiết hơn. Vì vậy, muốn kết luận chính xác thì phải xem **phiên bản plugin đang dùng**.

Ví dụ cấu hình Java 17 với Maven Compiler Plugin 3.x:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đây là fragment của `pom.xml`, không phải nội dung POM đầy đủ. Lệnh thường dùng:

```bash
mvn compile
mvn test
mvn clean verify
```

`mvn compile` thực hiện các phase đến `compile`; `mvn test` chạy tiếp phần test; `mvn clean verify` thực hiện clean lifecycle rồi default lifecycle đến verify. Với dự án multi-module, Maven reactor sắp xếp module theo phụ thuộc; phạm vi tái biên dịch trong mỗi module do compiler plugin quản lý.

**Điểm kiểm tra:** Nếu thay đổi API module A nhưng module B vẫn chạy bytecode cũ, kiểm tra B đã thực sự build bằng bản A vừa tạo chưa, Maven reactor đang chọn module nào, có `-am` khi dùng `-pl` không, và classpath có JAR cũ trong local repository hay không.

## 7. Khi nào chỉ build tăng dần là đủ?

Trong quy trình phát triển bình thường, trước tiên **build lại mục tiêu liên quan** và để công cụ tự quản lý đầu ra:

- Sửa thân phương thức, sửa lỗi logic, thêm test, cập nhật resource với input được khai báo đúng: chạy task tương ứng thường là đủ.
- Đổi public API trong multi-module: chạy build có bao gồm các module tiêu thụ và test liên quan; không cần mặc định xóa mọi output.
- Đổi version dependency/JDK/compiler option: build tool chuẩn có thể phát hiện và invalidation phù hợp nếu cấu hình đúng; xác minh log và đầu ra.
- Đổi annotation processor hoặc generated source: chạy lại các task sinh mã/biên dịch liên quan, kiểm tra đầu vào được khai báo.

Build bình thường sau khi đổi API vẫn phải compile các consumer cần thiết; incremental *chính xác* có nghĩa là chọn đúng tập bị ảnh hưởng, không có nghĩa lúc nào cũng biên dịch ít nhất có thể bất kể độ an toàn.

## 8. Khi nào cần build sạch?

`clean` thường xóa thư mục output do công cụ build quản lý (`build/` của Gradle, `target/` của Maven). Nó không phải lệnh “làm sạch toàn bộ máy”: dependency cache, IDE cache, Gradle user home, Maven local repository và artifact đã phát hành thường không bị xóa theo `clean` mặc định.

Ưu tiên clean khi có **bằng chứng đáng tin rằng trạng thái output đã mất tính nhất quán**, chẳng hạn:

1. **Lớp sinh ra từ nguồn đã xóa/đổi tên vẫn còn trong output** và được đóng gói/chạy nhầm; công cụ sinh mã hoặc task tùy biến không dọn stale outputs đúng cách.
2. **Nhiều phiên bản build/plugin/toolchain hoặc task tùy biến đã ghi trực tiếp cùng thư mục output**, khiến lịch sử đầu ra không còn đáng tin.
3. **Build tăng dần khác build từ trạng thái sạch** (ví dụ cùng commit mà sản phẩm JAR hoặc test khác biệt); cần clean để xác nhận và khoanh vùng nguyên nhân.
4. **Di trú cấu trúc lớn** (đổi source set, layout sản phẩm, processor hoặc generator) mà contract dọn stale outputs chưa được đảm bảo.
5. **Tạo bản phát hành hay xác minh CI cần chứng minh khả năng build từ đầu**, theo quy trình của dự án.

Lệnh Gradle:

```bash
./gradlew clean build
```

Lệnh Maven:

```bash
mvn clean verify
```

Sau clean, việc biên dịch được làm lại từ trạng thái output cục bộ trống; riêng **Gradle build cache** vẫn có thể tái sử dụng output hợp lệ nếu bật. Nếu yêu cầu kiểm tra thực sự cần task chạy mà không dùng build cache, có thể thử:

```bash
./gradlew clean build --no-build-cache
```

Tùy mục đích điều tra, `--rerun-tasks` ép chạy lại task Gradle dù up-to-date checks thông thường có thể skip chúng. Các cờ này dùng để **chẩn đoán có chủ đích**, không nên cấu hình thành thói quen cho mọi build.

### Trường hợp clean không giải quyết tận gốc

- Thiếu `inputs` hoặc `outputs` trong custom task: clean có thể che lỗi một lần, nhưng lần build sau vẫn có thể dùng output sai.
- Dependency sai version hoặc trùng lớp trên classpath: cần sửa dependency resolution, không chỉ xóa `build/`.
- App đang chạy process/JAR cũ: phải khởi động lại đúng artifact, xác nhận classpath runtime.
- Cấu hình JDK khác nhau giữa terminal, IDE và CI: phải thống nhất toolchain/`--release`, kiểm tra môi trường chạy.
- Annotation processor không ổn định hoặc sinh đầu ra không xác định: cần sửa processor và hợp đồng input/output.

Vì thế “cứ `clean` là hết lỗi” không phải chiến lược build đáng tin; nó có thể làm chậm build và che lỗi cấu hình theo dõi thay đổi.

## 9. Phân biệt các mức độ làm mới để chẩn đoán nhanh

| Mục tiêu | Lựa chọn hợp lý | Điều được kiểm tra |
|---|---|---|
| Sửa một file Java và muốn chạy lại chương trình | `./gradlew classes` hoặc `mvn compile` | Build cập nhật những output cần thiết |
| Kiểm tra vì sao task không chạy | `./gradlew compileJava --info` | Lý do task up-to-date/invalidation và hoạt động của compiler |
| Kiểm tra test sau thay đổi API | `./gradlew test` hoặc `mvn test` | Compile main/test và chạy test tương ứng |
| Nghi build cache cho ra output không mong đợi | `./gradlew build --no-build-cache` | Không tải/ghi build cache trong lượt kiểm tra này |
| Nghi task bị skip nhầm | `./gradlew build --rerun-tasks` | Ép task thực thi thay vì dựa vào trạng thái up-to-date |
| Nghi stale classes/resources còn sót | `./gradlew clean build` hoặc `mvn clean verify` | Tái tạo đầu ra sau khi xóa output của project |
| Kiểm chứng phát hành từ trạng thái sạch | Clean build trong môi trường CI độc lập | Khả năng tái dựng từ mã và dependency được khóa/kiểm soát |

Các lệnh là ví dụ trên Unix/macOS với Gradle Wrapper; Windows dùng `gradlew.bat` và Maven cần cài đặt/Wrapper tương ứng. Không thêm `clean` trước mọi lệnh theo phản xạ.

## 10. Quy trình điều tra khi kết quả build có vẻ sai

**Bước 1 — Xác nhận đúng artifact và môi trường.** Kiểm tra mình đang chạy output từ `build/classes`, `target/classes`, JAR vừa build hay một JAR từ repository. Kiểm tra `java -version`, compiler toolchain, module/branch hiện tại và runtime classpath.

**Bước 2 — Xác định file, input hoặc API nào đã đổi.** Hỏi: thay đổi chỉ ở thân phương thức hay cả API? Có hằng compile-time, annotation, generator, dependency JAR, compiler option hoặc resource không? Ghi rõ task tiêu thụ đầu vào đó.

**Bước 3 — Quan sát build không clean.** Với Gradle:

```bash
./gradlew compileJava --info
./gradlew test --console=verbose
```

Trong multi-project, dùng đường dẫn task có namespace như `:core:compileJava` hoặc `:app:test`. Xem task trạng thái `UP-TO-DATE`, `FROM-CACHE`, recompile và lý do. Với Maven:

```bash
mvn -X compile
```

Log debug có thể lớn; tìm phần Maven Compiler Plugin và dependency/classpath liên quan. Đọc log theo phiên bản tool đang dùng, không suy diễn từ một từ khóa đơn lẻ.

**Bước 4 — Thử cách cô lập nhỏ nhất.** Nếu nghi cache, tắt build cache một lượt; nếu nghi up-to-date, chạy lại task có chủ đích; nếu nghi stale generated class, kiểm tra thư mục output của đúng task. Không xóa cả Maven repository hoặc Gradle user cache khi chưa có chứng cứ liên quan.

**Bước 5 — So sánh với clean build.** Chỉ khi cần, chạy clean build rồi so sánh lỗi, nội dung JAR, test và classpath. Nếu clean sửa được vấn đề nhưng incremental vẫn sai, hãy tìm **đầu vào/output chưa khai báo**, lớp cũ chưa dọn, processor không incremental hoặc task phụ thuộc thiếu.

**Bước 6 — Sửa nguyên nhân và thêm kiểm chứng có ý nghĩa.** Ví dụ task sinh source phải khai báo file cấu hình mà nó đọc là input, thư mục generated output là output, và liên kết task biên dịch phụ thuộc task sinh source. Một bài test thay đổi API và rebuild consumer có thể phát hiện regression thực tế.

## 11. Những ngộ nhận và lỗi thường gặp

**“Chỉ sửa implementation nên không cần chạy build.”** Sai: implementation mới vẫn phải được biên dịch và đóng gói. Cái thường được *tránh* là biên dịch lại những consumer có ABI dependency không đổi.

**“Mọi thay đổi public đều làm compile toàn repo.”** Không nhất thiết: chỉ những phần phụ thuộc bị ảnh hưởng cần được xem xét; mức độ chính xác tùy build tool, processor và cấu hình. Một số compiler/plugin có thể chọn biên dịch lại cả module cho an toàn.

**“`UP-TO-DATE` nghĩa là mã mới chắc chắn đúng.”** Nó chỉ có nghĩa công cụ cho rằng task đã hợp lệ theo đầu vào/đầu ra được khai báo. Đầu vào bị bỏ sót có thể làm kết luận sai.

**“`clean` cũng xóa dependency cache.”** Clean thông thường dọn output project, không phải toàn bộ cache Maven/Gradle trong thư mục người dùng.

**“Chỉ nhìn timestamp là đủ.”** Timestamp không hiểu đầy đủ dependency graph, ABI, constants, generated outputs, compiler flags và classpath.

**“Build lại `lib` là đủ sau khi đổi chữ ký API.”** Consumer từng compile với descriptor cũ cũng phải được cập nhật; thí nghiệm `Price` và `Main` cho thấy rủi ro liên kết.

**“Maven và Gradle có incremental compilation giống nhau.”** Thuật toán/phạm vi khác nhau tùy plugin/version. Kiểm tra hành vi thực tế thay vì suy từ tên tính năng.

## 12. Bài tập tự kiểm tra

**Tình huống A.** Trong module `:core`, chỉ sửa `return price * quantity;` thành `return Math.multiplyExact(price, quantity);`; chữ ký method không đổi. Điều gì nên xảy ra?

*Gợi ý đáp án:* Core cần biên dịch lại phần ảnh hưởng; app consumer có thể được Gradle tránh biên dịch vì ABI không đổi. Runtime có thể thay đổi do `Math.multiplyExact` ném `ArithmeticException` khi tràn số.

**Tình huống B.** Đổi `public static int total(int, int)` thành `public static long total(int, int)`, rồi chỉ compile file định nghĩa. Vì sao app cũ có thể ném `NoSuchMethodError`?

*Gợi ý đáp án:* Kiểu trả về là một phần của JVM method descriptor. Consumer bytecode vẫn liên kết tới descriptor `(II)I`, còn provider mới có `(II)J`. Phải recompile các consumer phụ thuộc vào API đã thay đổi.

**Tình huống C.** Chạy `clean build` thì test đúng; build tăng dần lần sau lại sai khi sửa YAML cho bộ sinh mã. Nên làm gì?

*Gợi ý đáp án:* Kiểm tra YAML có được khai báo là input của generation/compile task không, đầu ra có được khai báo và loại bỏ đúng khi input đổi không, task dependency được nối đúng không. Sửa hợp đồng build; clean chỉ là phép thử để chỉ ra sự khác biệt.

**Tình huống D.** Compile Java báo `UP-TO-DATE` nhưng ứng dụng vẫn chạy logic cũ. Ba vị trí cần kiểm tra là gì?

*Gợi ý đáp án:* (1) Có đang chạy class/JAR mới hay process cũ; (2) mã nguồn sửa có nằm đúng source set/module/task input không; (3) runtime classpath có bản JAR/class trùng hoặc dependency version cũ không.

## 13. Checklist áp dụng trong dự án thực tế

- Xác định rõ source set, task, module và compile/runtime classpath.
- Dùng Java toolchain/`--release` nhất quán; khóa phiên bản công cụ build, plugin và dependency phù hợp.
- Khai báo chính xác input/output cho custom task và code generator; tách annotation processor path.
- Kiểm chứng thay đổi API có kéo theo compile/test của consumer chịu ảnh hưởng.
- Dùng log task để phân biệt up-to-date, cache hit, compile incremental và compile avoidance.
- Chỉ clean khi cần kiểm chứng trạng thái sạch hoặc xử lý nghi vấn stale outputs; sau đó sửa gốc nếu incremental có lỗi.
- Với CI và bản phát hành, bảo đảm build có thể tái lập từ môi trường kiểm soát, ngay cả khi local build tận dụng incremental và cache.

## Tài liệu chính thức để đọc sâu

- [Gradle — The Java Plugin: incremental compilation, compilation avoidance, annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_builds.html)
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html)
- [Apache Maven Compiler Plugin 3.x — compile goal](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven Compiler Plugin 4.x — incrementalCompilation](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/compile-mojo.html)

Các tài liệu Gradle/Maven có thể cập nhật theo phiên bản; khi chẩn đoán hệ thống cụ thể, ưu tiên tài liệu khớp version build tool và plugin của chính dự án.