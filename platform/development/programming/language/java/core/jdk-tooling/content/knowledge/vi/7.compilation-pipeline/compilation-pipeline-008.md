# Incremental compilation trong Java

Incremental compilation là cách build lại phần mã nguồn bị ảnh hưởng sau một thay đổi, thay vì biên dịch lại toàn bộ dự án ở mọi lần chỉnh sửa. Với dự án Java có hàng nghìn lớp, cách làm này giúp rút ngắn vòng lặp sửa mã, biên dịch và kiểm tra.

Tuy nhiên, xác định phần nào cần biên dịch lại đòi hỏi hiểu quan hệ phụ thuộc giữa các lớp. Một thay đổi chỉ nằm trong thân phương thức thường ít ảnh hưởng hơn thay đổi chữ ký public, lớp cha, interface hoặc hằng số compile-time. Nếu bỏ sót lớp phụ thuộc, build có thể thành công nhưng chương trình chạy với bytecode cũ và phát sinh lỗi liên kết hoặc kết quả không cập nhật.

## 1. Full compilation và incremental compilation

**Full compilation** biên dịch toàn bộ tập mã nguồn của một module hoặc dự án theo cấu hình build hiện tại. Cách này tốn thời gian hơn khi dự án lớn, nhưng dễ tái lập và hữu ích khi kiểm tra trạng thái sạch.

**Incremental compilation** chỉ biên dịch lại các compilation unit bị thay đổi và những unit cần được cập nhật vì phụ thuộc của chúng đã thay đổi. Một compilation unit thường là một tệp nguồn Java được biên dịch như một đơn vị.

Ví dụ, dự án có ba lớp:

- TaxPolicy tính thuế.
- Invoice gọi TaxPolicy để tính tổng hóa đơn.
- App gọi Invoice và in kết quả.

Nếu chỉ thay đổi công thức bên trong TaxPolicy mà giữ nguyên tên phương thức, kiểu tham số và kiểu trả về, các lớp gọi nó thường không cần biên dịch lại. Nếu đổi chữ ký phương thức, Invoice có thể cần biên dịch lại vì bytecode của nó đang gọi phương thức theo descriptor cũ.

| Loại thay đổi | Phạm vi biên dịch lại thường cần |
|---|---|
| Sửa comment hoặc khoảng trắng | Không cần biên dịch lại về mặt bytecode nếu công cụ build nhận diện thay đổi không ảnh hưởng; công cụ vẫn có thể biên dịch lại tệp đã đổi. |
| Sửa thân phương thức nhưng giữ API | Thường chỉ cần biên dịch lại lớp đã đổi. |
| Đổi chữ ký phương thức public | Biên dịch lại lớp thay đổi và các lớp nguồn phụ thuộc có sử dụng chữ ký đó. |
| Đổi lớp cha hoặc interface | Có thể ảnh hưởng các lớp con, lớp triển khai và mã gọi liên quan. |
| Đổi hằng số compile-time | Cần biên dịch lại các lớp tiêu thụ hằng số vì giá trị có thể đã được nhúng vào bytecode của chúng. |
| Đổi dependency, compiler option hoặc module descriptor | Có thể làm mất hiệu lực kết quả biên dịch của nhiều lớp hoặc toàn module. |

Đây là hướng dẫn khái quát. Tập lớp cần biên dịch lại phụ thuộc vào loại thay đổi, cách mã được sử dụng và khả năng phân tích dependency của build tool.

## 2. javac làm gì và không làm gì?

Javac là trình biên dịch. Nó nhận các tệp nguồn và tùy chọn của lần gọi hiện tại, kiểm tra kiểu, phân giải dependency và tạo bytecode.

Javac có thể tìm thêm tệp nguồn được tham chiếu thông qua source path nếu các tệp đó chưa được cung cấp trực tiếp. Ví dụ:

~~~bash
javac -sourcepath src/main/java -d out src/main/java/com/acme/app/App.java
~~~

Trong lần gọi này, javac có thể tìm và biên dịch các tệp nguồn cần thiết để phân giải App.

Cơ chế tìm và biên dịch nguồn phụ thuộc trong một lần gọi **không đồng nghĩa với một hệ thống incremental build hoàn chỉnh**. Bản thân javac không quản lý lâu dài toàn bộ lịch sử build, dependency graph của dự án, cache đầu ra qua nhiều lần chạy, hoặc quyết định chính sách chạy test. Các công cụ như Gradle, Maven và IDE điều phối những phần việc đó bằng cách theo dõi đầu vào, đầu ra và quan hệ phụ thuộc.

Có thể gọi javac thủ công để biên dịch một tập nguồn đã xác định. Nhưng khi dự án lớn, việc tự quyết định mọi lớp phụ thuộc cần biên dịch lại rất dễ bỏ sót. Hãy dùng build tool có dependency analysis để thực hiện incremental compilation một cách nhất quán.

## 3. Ví dụ: chỉ biên dịch lại lớp có phần triển khai thay đổi

Tạo cấu trúc dự án:

~~~text
incremental-demo/
├── src/main/java/
│   ├── com/acme/pricing/
│   │   ├── TaxPolicy.java
│   │   └── Invoice.java
│   └── com/acme/app/
│       └── App.java
└── out/
~~~

Tệp src/main/java/com/acme/pricing/TaxPolicy.java:

~~~java
package com.acme.pricing;

public class TaxPolicy {
    public int taxFor(int subtotal) {
        return subtotal / 10;
    }
}
~~~

Tệp src/main/java/com/acme/pricing/Invoice.java:

~~~java
package com.acme.pricing;

public class Invoice {
    private final TaxPolicy policy = new TaxPolicy();

    public int totalFor(int subtotal) {
        return subtotal + policy.taxFor(subtotal);
    }
}
~~~

Tệp src/main/java/com/acme/app/App.java:

~~~java
package com.acme.app;

import com.acme.pricing.Invoice;

public class App {
    public static void main(String[] args) {
        System.out.println(new Invoice().totalFor(100));
    }
}
~~~

### Build lần đầu

Từ thư mục gốc incremental-demo, tạo thư mục đầu ra và biên dịch cả ba tệp:

~~~bash
mkdir -p out

javac -d out \
  src/main/java/com/acme/pricing/TaxPolicy.java \
  src/main/java/com/acme/pricing/Invoice.java \
  src/main/java/com/acme/app/App.java

java -cp out com.acme.app.App
~~~

Output:

~~~text
110
~~~

TaxPolicy tính thuế bằng 10% của subtotal, vì vậy tổng của 100 là 110.

### Chỉ thay đổi phần triển khai

Giả sử chính sách thuế thay đổi thành 20%, nhưng phương thức vẫn giữ nguyên chữ ký:

~~~java
package com.acme.pricing;

public class TaxPolicy {
    public int taxFor(int subtotal) {
        return subtotal / 5;
    }
}
~~~

Tên phương thức vẫn là taxFor, tham số vẫn là int và giá trị trả về vẫn là int. Chỉ phần thân phương thức thay đổi.

Có thể biên dịch lại riêng TaxPolicy, dùng out làm classpath để javac tìm những lớp đã biên dịch mà nó cần:

~~~bash
javac -cp out -d out src/main/java/com/acme/pricing/TaxPolicy.java

java -cp out com.acme.app.App
~~~

Output mới:

~~~text
120
~~~

Invoice.class và App.class vẫn dùng được vì hợp đồng nhị phân mà chúng gọi chưa thay đổi. Khi chạy, JVM nạp TaxPolicy.class mới nên kết quả đã cập nhật.

Ví dụ này cho thấy lợi ích của incremental compilation. Nó cũng giả định rằng thay đổi chỉ tác động tới phần triển khai và không làm thay đổi hành vi mà các lớp gọi phụ thuộc vào theo một hợp đồng khác.

## 4. Vì sao thay đổi API cần biên dịch lại lớp phụ thuộc?

Bytecode của lớp gọi chứa thông tin về phương thức mà nó sử dụng, gồm tên và descriptor của phương thức. Descriptor mô tả kiểu tham số và kiểu trả về ở mức JVM.

Giả sử TaxPolicy ban đầu có:

~~~java
public int taxFor(int subtotal) {
    return subtotal / 5;
}
~~~

Invoice đã biên dịch sẽ tham chiếu tới phương thức nhận int và trả về int. Nếu đổi phương thức thành:

~~~java
public int taxFor(long subtotal) {
    return (int) (subtotal / 5);
}
~~~

Descriptor của phương thức đã thay đổi. Nếu chỉ biên dịch TaxPolicy mới mà giữ Invoice.class cũ, Invoice vẫn cố gọi phương thức với descriptor cũ. Khi chạy, JVM có thể ném:

~~~text
java.lang.NoSuchMethodError
~~~

Cần biên dịch lại các lớp phụ thuộc bị ảnh hưởng:

~~~bash
javac -cp out -d out \
  src/main/java/com/acme/pricing/TaxPolicy.java \
  src/main/java/com/acme/pricing/Invoice.java \
  src/main/java/com/acme/app/App.java
~~~

Lệnh trên là cách bảo thủ để làm mới toàn bộ ba lớp trong ví dụ. Với dự án lớn, build tool phân tích dependency để chỉ biên dịch lại các lớp cần thiết.

Một số thay đổi khác cũng có thể làm thay đổi ABI hoặc ảnh hưởng mã tiêu thụ:

- Thêm, xóa hoặc đổi kiểu phương thức và field được sử dụng từ nơi khác.
- Thay đổi superclass hoặc interface được triển khai.
- Thay đổi khả năng truy cập khiến mã gọi không còn truy cập được.
- Thay đổi generic signature có thể làm mã nguồn phụ thuộc không biên dịch được dù descriptor sau type erasure không đổi.
- Thay đổi module descriptor, chẳng hạn exports hoặc requires, làm thay đổi khả năng đọc và truy cập module.

Không nên đánh giá tác động chỉ bằng cách nhìn xem thân phương thức có đổi hay không. Cần xem hợp đồng mà các lớp khác biên dịch dựa vào.

## 5. Hằng số compile-time và bytecode đã nhúng giá trị

Một trường hợp dễ bị bỏ sót là hằng số compile-time. Ví dụ:

~~~java
package com.acme.config;

public class AppConfig {
    public static final int RETRY_LIMIT = 3;
}
~~~

Lớp sử dụng:

~~~java
package com.acme.app;

import com.acme.config.AppConfig;

public class RetryJob {
    public static void main(String[] args) {
        System.out.println(AppConfig.RETRY_LIMIT);
    }
}
~~~

Khi biên dịch, giá trị hằng số phù hợp điều kiện compile-time constant có thể được nhúng trực tiếp vào bytecode của lớp sử dụng. Nếu đổi RETRY_LIMIT từ 3 thành 5 và chỉ biên dịch lại AppConfig, RetryJob.class cũ vẫn có thể tiếp tục in 3.

Vì vậy, khi thay đổi compile-time constant, cần biên dịch lại các lớp tiêu thụ hằng số đó. Đây là một lý do quan trọng để build tool theo dõi dependency ở mức sâu hơn việc chỉ kiểm tra tên lớp có tồn tại hay không.

Không phải mọi field static final đều là compile-time constant. Đặc tính này áp dụng cho các biến constant theo định nghĩa của Java, chẳng hạn biến final có kiểu nguyên thủy hoặc String và được khởi tạo bằng constant expression.

## 6. Dependency graph và phạm vi invalidation

Build tool có thể mô hình hóa các lớp hoặc compilation unit thành một đồ thị phụ thuộc. Một cạnh từ A tới B có nghĩa là A phụ thuộc vào B trong quá trình biên dịch hoặc sử dụng.

Ví dụ:

~~~text
App
 |
 v
Invoice
 |
 v
TaxPolicy
~~~

Khi TaxPolicy thay đổi:

- Nếu chỉ thay đổi phần triển khai mà API giữ nguyên, Invoice và App thường không cần biên dịch lại.
- Nếu thay đổi API mà Invoice sử dụng, Invoice phải được biên dịch lại; những lớp phụ thuộc vào API của Invoice cũng có thể cần cập nhật.
- Nếu thay đổi một thành phần nền tảng dùng chung, phạm vi ảnh hưởng có thể lan tới nhiều module.

Incremental compiler cần xác định **invalidation set**: tập đầu ra không còn đáng tin cậy sau khi đầu vào thay đổi. Build tool sau đó biên dịch lại tập nguồn tương ứng và cập nhật kết quả phân tích dependency.

Phạm vi invalidation không nhất thiết là toàn bộ cây phụ thuộc theo mọi hướng. Nhiều build tool có thể phân tích ABI để tránh biên dịch lại người gọi khi chỉ có implementation body thay đổi. Cách phân tích cụ thể phụ thuộc công cụ, compiler, ngôn ngữ và cấu hình dự án.

## 7. Gradle và incremental Java compilation

Gradle hỗ trợ incremental compilation cho các task JavaCompile. Gradle theo dõi đầu vào của task và có thể dùng phân tích classpath/ABI để xác định những lớp cần biên dịch lại khi mã nguồn hoặc dependency thay đổi.

Ví dụ cấu hình Java toolchain và compile task:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.incremental = true
    options.compilerArgs += ['-Xlint:all']
}
~~~

Trong ví dụ, toolchain chọn JDK 17 cho tác vụ Java có hỗ trợ toolchain. Cấu hình incremental yêu cầu Gradle dùng chế độ incremental compilation cho task JavaCompile. Gradle có thể quyết định biên dịch lại một phần hoặc toàn bộ tùy thay đổi, trạng thái phân tích và các điều kiện hỗ trợ.

Chạy task biên dịch:

~~~bash
./gradlew compileJava
~~~

Trên Windows:

~~~powershell
.\gradlew.bat compileJava
~~~

Để xem thêm thông tin về các task và quá trình thực thi, có thể dùng:

~~~bash
./gradlew compileJava --info
~~~

Incremental compilation không có nghĩa là mọi lần chạy task đều chỉ biên dịch đúng một tệp. Thay đổi cấu hình compiler, JDK, classpath, annotation processor hoặc trạng thái build có thể khiến Gradle phải biên dịch lại phạm vi lớn hơn.

Gradle cũng hỗ trợ incremental annotation processing khi processor khai báo loại xử lý phù hợp và đáp ứng hợp đồng của Gradle. Processor dạng isolating tạo đầu ra gắn với từng đầu vào; processor dạng aggregating có thể tổng hợp thông tin từ nhiều đầu vào. Processor không khai báo hoặc không đáp ứng cơ chế incremental có thể khiến quá trình biên dịch phải dùng chiến lược rộng hơn.

## 8. Maven và incremental compilation

Maven tổ chức build qua lifecycle và các plugin. Maven Compiler Plugin gọi compiler Java với các nguồn và tùy chọn được cấu hình trong dự án.

Ví dụ cấu hình phiên bản Java và compiler arguments:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
        <compilerArgs>
            <arg>-Xlint:all</arg>
        </compilerArgs>
    </configuration>
</plugin>
~~~

Chạy compile:

~~~bash
mvn compile
~~~

Hành vi biên dịch lại chính xác phụ thuộc phiên bản Maven Compiler Plugin, compiler được chọn, cấu hình incrementalCompilation và các đầu vào mà plugin theo dõi. Không nên mặc định rằng Maven và Gradle sử dụng cùng một thuật toán incremental compilation hoặc cùng cách phân tích ABI.

Khi cần xác nhận toàn bộ dự án có thể build từ trạng thái đầu ra sạch, dùng:

~~~bash
mvn clean compile
~~~

Lệnh clean loại bỏ output build trước đó theo lifecycle của dự án, sau đó compile tạo lại đầu ra. Đây là phép kiểm tra hữu ích sau khi thay đổi dependency, compiler plugin, annotation processor hoặc cấu hình build.

## 9. Annotation processing và mã nguồn được sinh

Annotation processor có thể tạo thêm tệp .java hoặc tài nguyên trong lúc biên dịch. Ví dụ, processor tạo mapper, metadata hoặc lớp hỗ trợ từ annotation trong mã nguồn.

Điều này làm incremental compilation phức tạp hơn vì đầu vào của một lần biên dịch không chỉ là các tệp Java do lập trình viên viết. Khi annotation thay đổi, processor có thể cần chạy lại và sinh ra các lớp khác. Một processor tổng hợp thông tin từ nhiều lớp có thể làm thay đổi đầu ra khi bất kỳ một trong các lớp đó thay đổi.

Cần lưu ý:

- Processor có thể tạo nguồn phụ thuộc vào một hoặc nhiều compilation unit.
- Thay đổi processor hoặc processor path có thể làm mất hiệu lực đầu ra đã sinh.
- Xóa một lớp nguồn có thể đòi hỏi xóa cả các tệp được sinh từ lớp đó.
- Processor không hỗ trợ incremental có thể khiến build tool phải biên dịch lại rộng hơn.
- Không nên chỉnh sửa trực tiếp tệp generated source nếu chúng sẽ được sinh lại ở lần build tiếp theo.

Hãy cấu hình annotation processor qua build tool và lưu generated source trong thư mục build riêng. Việc đó giúp phân biệt nguồn do người viết với nguồn được tạo tự động, đồng thời giảm nguy cơ giữ lại tệp sinh cũ.

## 10. Xóa lớp và stale output

Incremental compilation không chỉ cần biết tệp nào phải biên dịch lại. Nó còn phải xử lý đầu ra cũ không còn tương ứng với nguồn hiện tại.

Ví dụ, nếu xóa:

~~~text
src/main/java/com/acme/legacy/OldService.java
~~~

thì tệp:

~~~text
out/com/acme/legacy/OldService.class
~~~

có thể vẫn còn trên đĩa nếu công cụ build không xóa output tương ứng. Một lớp cũ như vậy có thể khiến chương trình vẫn nạp được mã đã bị xóa khỏi source tree, làm kết quả build khó hiểu.

Đây gọi là stale output. Các trường hợp tương tự có thể xảy ra khi đổi tên lớp, chuyển package, xóa resource hoặc thay đổi mã được sinh.

Build tool cần theo dõi output của task để xóa những tệp không còn được tạo ra. Nếu dùng javac thủ công, việc dọn output directory có thể cần thực hiện rõ ràng.

Trên Linux/macOS, trong ví dụ dự án có thể xóa thư mục đầu ra trước khi full build:

~~~bash
rm -rf out
mkdir -p out
~~~

Trên PowerShell:

~~~powershell
if (Test-Path out) {
    Remove-Item out -Recurse -Force
}
New-Item -ItemType Directory -Force out | Out-Null
~~~

Chỉ thực hiện thao tác xóa trên thư mục build đã xác định của dự án. Không dùng lệnh xóa đệ quy với đường dẫn chưa kiểm tra.

## 11. Những thay đổi có thể làm mất hiệu lực incremental state

Build tool thường cần biên dịch lại nhiều hơn khi một trong các đầu vào nền tảng thay đổi:

- Phiên bản JDK hoặc compiler.
- Compiler arguments như --release, -encoding, -parameters hoặc tùy chọn lint.
- Classpath, module path hoặc phiên bản thư viện.
- Module descriptor và quan hệ requires/exports.
- Annotation processor, processor path hoặc cấu hình xử lý annotation.
- Cấu hình source set, source root hoặc generated source directory.
- Build script, plugin hoặc cấu hình task.
- Trạng thái cache/analysis bị thiếu, hỏng hoặc không tương thích.

Những thay đổi này có thể ảnh hưởng cách javac phân tích mã hoặc cách build tool xác định dependency. Trong trường hợp không thể xác minh trạng thái incremental, build tool có thể chạy full compilation để bảo đảm tính đúng đắn.

## 12. Incremental compilation không thay thế testing

Biên dịch thành công chỉ xác nhận các điều kiện compile-time mà compiler kiểm tra. Nó không chứng minh logic nghiệp vụ đúng hoặc chương trình chạy đúng với mọi dữ liệu.

Một thay đổi implementation có thể giữ nguyên API nhưng làm thay đổi kết quả tính toán. Ví dụ, đổi tỷ lệ thuế trong TaxPolicy không buộc Invoice phải biên dịch lại, nhưng vẫn cần kiểm thử để xác nhận nghiệp vụ mới đúng.

Nên tách các hoạt động:

1. **Incremental compile:** kiểm tra và tạo lại bytecode cho phần bị ảnh hưởng.
2. **Unit test:** xác nhận hành vi của lớp hoặc thành phần đã đổi.
3. **Integration test:** xác nhận các lớp và module phối hợp đúng.
4. **Full clean build:** xác nhận toàn bộ dự án có thể được tạo lại từ đầu.
5. **Packaging/deployment test:** xác nhận artifact cuối cùng chứa đúng lớp, resource và dependency.

Tùy rủi ro của thay đổi, CI có thể chạy test liên quan nhanh trong vòng lặp phát triển và vẫn chạy bộ kiểm tra rộng hơn trước khi merge hoặc phát hành.

## 13. Lỗi thường gặp khi dùng incremental compilation

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chạy chương trình vẫn thấy kết quả cũ | Chưa biên dịch lại lớp chứa logic vừa đổi hoặc runtime đang dùng thư mục output khác. | Kiểm tra output directory và classpath; xác nhận timestamp/nội dung lớp mới. |
| NoSuchMethodError sau khi đổi chữ ký API | Lớp gọi vẫn chứa bytecode tham chiếu descriptor cũ. | Biên dịch lại các lớp nguồn phụ thuộc hoặc chạy clean build. |
| NoClassDefFoundError sau khi chuyển package | Lớp đầu ra cũ bị xóa hoặc classpath/module path không còn trỏ đúng vị trí. | Kiểm tra package, output tree và runtime path. |
| Lớp đã xóa vẫn chạy được | Tệp .class cũ còn trong output directory. | Dùng clean build hoặc xóa output được quản lý rồi biên dịch lại. |
| Gradle/Maven biên dịch nhiều hơn dự kiến | Thay đổi classpath, compiler options, processor hoặc build state làm invalidation rộng. | Xem log task, kiểm tra dependency và cấu hình compiler. |
| Build incremental thành công nhưng clean build thất bại | Output cũ đang che giấu dependency hoặc lớp sinh bị thiếu. | Chạy clean build và sửa khai báo dependency/processor/output. |
| IDE và CI cho kết quả khác nhau | Khác JDK, compiler options, source roots hoặc build tool configuration. | Đồng bộ cấu hình dự án và xác minh bằng lệnh build chính thức. |

## 14. Quy trình làm việc khuyến nghị

Khi sửa một dự án Java, có thể áp dụng quy trình sau:

1. Xác định lớp và module đang thay đổi.
2. Xác định thay đổi chỉ nằm trong implementation hay làm thay đổi API/ABI.
3. Kiểm tra những lớp, module, generated source và resource phụ thuộc.
4. Chạy incremental compile qua build tool để có phản hồi nhanh.
5. Chạy test phù hợp với thay đổi.
6. Nếu thay đổi dependency, compiler option, processor hoặc build script, kiểm tra phạm vi invalidation và chạy build rộng hơn.
7. Chạy clean build trước khi tích hợp hoặc phát hành khi cần xác minh khả năng tái tạo.
8. Nếu incremental build và clean build cho kết quả khác nhau, điều tra stale output, dependency bị khai báo thiếu hoặc cache không hợp lệ.

Incremental compilation giúp tiết kiệm thời gian nhưng chỉ đáng tin khi dependency và output được quản lý chính xác. Hãy để build tool theo dõi đầu vào và quan hệ phụ thuộc, hiểu khi nào thay đổi implementation có thể giữ nguyên consumer bytecode, và khi nào API hoặc cấu hình buộc phải biên dịch lại phạm vi lớn hơn. Kết hợp incremental build với test và clean build giúp vừa có vòng lặp phát triển nhanh vừa giữ được độ tin cậy của artifact Java.
