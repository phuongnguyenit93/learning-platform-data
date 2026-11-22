# Manifest, chữ ký JAR và service metadata sau khi đóng gói lại

Khi nâng JDK, đổi Maven/Gradle plugin hoặc chuyển từ nhiều dependency JAR sang *fat JAR*, *uber JAR*, *shaded JAR*, ứng dụng Java có thể biên dịch bình thường nhưng lỗi khi triển khai. Một nguyên nhân thường bị bỏ qua là **metadata ở bên trong artifact** đã bị ghi đè, lọc bỏ hoặc không còn phù hợp với nội dung sau khi đóng gói. Những thành phần quan trọng gồm `META-INF/MANIFEST.MF`, các file chữ ký JAR và `META-INF/services` dùng bởi `ServiceLoader`.

Ví dụ: JAR đã có `Main-Class` nhưng task tạo artifact cuối làm mất thuộc tính này; hai thư viện cùng đăng ký provider cho một SPI nhưng trình đóng gói chỉ giữ một file service; hoặc dependency được ký số đã bị thay đổi class/manifest trong bước shade mà signature block cũ vẫn được sao chép. Các trường hợp này có biểu hiện khác nhau: `no main manifest attribute`, `ServiceConfigurationError`, `SecurityException` hoặc kết quả nghiệp vụ thiếu chức năng mà không có lỗi ngay lúc startup.

Bài học trình bày chức năng của các metadata, cách giữ hợp đồng khi repack/shade/relocate, cách xử lý chữ ký đúng chính sách bảo mật, đặc điểm JPMS và multi-release JAR, cùng quy trình kiểm tra **artifact cuối cùng** trong Java Advance Compatibility Migration.

## 1. JAR không chỉ chứa `.class`

Một JAR là archive dựa trên ZIP. Ngoài bytecode, nó còn chứa resources và các quy tắc runtime.

~~~text
payments-client.jar
├── META-INF/
│   ├── MANIFEST.MF
│   ├── services/
│   │   └── com.example.spi.PaymentProvider
│   ├── LICENSE
│   └── NOTICE
├── com/example/api/PaymentClient.class
├── com/example/impl/FastPaymentProvider.class
└── config/defaults.properties
~~~

Một signed JAR có thể có thêm:

~~~text
META-INF/
├── MANIFEST.MF
├── RELEASE.SF
└── RELEASE.RSA
~~~

Một multi-release JAR có thể có:

~~~text
META-INF/versions/
├── 11/com/example/runtime/PlatformSupport.class
└── 17/com/example/runtime/PlatformSupport.class
~~~

Những đường dẫn này ảnh hưởng đến cách Java launcher, class loader, module system, JAR verifier và framework sử dụng artifact. Không nên coi các file trong `META-INF` là tài nguyên phụ có thể xóa khi tối ưu dung lượng.

| Thành phần | Chức năng | Rủi ro sau khi repack |
|---|---|---|
| `META-INF/MANIFEST.MF` | Entry point, class path, thông tin archive, multi-release, module name | Khởi động sai, classpath thiếu, mất hành vi MR-JAR |
| `META-INF/*.SF` và signature blocks | Dữ liệu kiểm tra chữ ký của entries đã ký | Signature digest không khớp hoặc mất provenance |
| `META-INF/services/*` | Đăng ký providers cho Java SPI | Mất provider, provider name sai |
| `module-info.class` | Descriptor của explicit Java module | Module resolution/access/service binding lỗi |
| `META-INF/versions/*` | Biến thể class cho các JDK mới | Chọn class sai hoặc mất tối ưu |
| Metadata của framework | Đăng ký auto-configuration, extensions, resources | Framework bỏ qua tính năng |
| `LICENSE`/`NOTICE` | Thông tin phân phối và giấy phép | Vi phạm yêu cầu attribution/distribution |

## 2. “Đóng gói lại” có thể bao gồm những thao tác nào?

Các build thường làm một hoặc nhiều việc sau:

- Tạo một JAR từ các class của project.
- Gộp toàn bộ dependency classes vào một uber JAR.
- **Relocation:** đổi package names của thư viện để tránh xung đột.
- **Resource transformation:** gộp hoặc viết lại resource trùng đường dẫn.
- **Minimization:** loại bỏ class/resource được cho là không dùng.
- Tạo executable JAR với launcher và nested dependencies.
- Đổi manifest hoặc thêm thông tin build.
- Ký artifact cuối cùng.

Không phải tất cả các kiểu đóng gói tạo cùng cấu trúc. Một flat shaded JAR khác với Spring Boot executable JAR chứa nested JAR. Một modular JAR có `module-info.class` khác automatic module chỉ có `Automatic-Module-Name` trong manifest.

Sơ đồ rủi ro:

~~~text
Source + dependency JARs
             |
             v
Compile/Test
             |       Unit test có thể chạy từ target/classes
             v
Package / Shade / Repackage
             |
             +--> MANIFEST bị thay
             +--> signature files không còn phù hợp
             +--> META-INF/services bị ghi đè
             +--> classes/metadata bị relocation
             +--> versioned entries bị biến đổi
             v
Artifact cuối được deploy
             |
             v
java -jar / module launcher / ServiceLoader
             |
             v
Lỗi chỉ xuất hiện ở runtime
~~~

**BUILD SUCCESS chưa chứng minh artifact runtime đúng.** Test chỉ chạy trước bước package có thể hoàn toàn không phát hiện lỗi metadata.

## 3. Manifest: cấu trúc và ý nghĩa

Manifest thường nằm ở `META-INF/MANIFEST.MF`. Nó có phần chính với các thuộc tính toàn cục và có thể có các section riêng cho từng entry/package. Định dạng manifest có quy tắc về ký tự, continuation lines và dòng trống phân cách sections; nên để `jar` hoặc build plugin tạo ra thay vì tự nối text tùy ý.

Ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Title: Payment Service
Implementation-Version: 2.3.0
Automatic-Module-Name: com.example.payment
Multi-Release: true

~~~

Các thuộc tính ở trên không nhất thiết cùng xuất hiện trong mọi JAR. `Main-Class` cần thiết khi muốn launcher chuẩn chạy entry point tương ứng bằng `java -jar`. `Automatic-Module-Name` hữu ích với automatic modules. `Multi-Release: true` chỉ phù hợp khi artifact được thiết kế như MR-JAR.

### 3.1. `Main-Class` và `java -jar`

Ví dụ manifest của một ứng dụng đơn giản:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

~~~

Tạo archive với JDK `jar`:

~~~bash
jar --create --file app.jar --manifest manifest.mf -C out/classes .
java -jar app.jar
~~~

Ví dụ giả định `out/classes` có `com/example/app/Main.class` với `main` method phù hợp, và các dependencies đã được cung cấp đúng.

Nếu đóng gói lại mà mất entry point:

~~~text
no main manifest attribute, in app.jar
~~~

Nếu ghi tên class sai, JVM có thể báo không tìm được main class. Điều cần xem là **manifest bên trong artifact cuối**, không phải POM/Gradle configuration của một JAR trung gian.

### 3.2. `Class-Path` không tương đương nested JAR

Manifest có thể khai báo:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/common.jar lib/jdbc-driver.jar

~~~

Phân phối dự kiến:

~~~text
distribution/
├── app.jar
└── lib/
    ├── common.jar
    └── jdbc-driver.jar
~~~

Đường dẫn trong manifest được diễn giải theo quy tắc JAR Class-Path, thường liên quan đến vị trí chứa JAR. Nếu di chuyển `app.jar` mà thiếu `lib`, class loader có thể không tìm được dependency.

Cần phân biệt:

- `Class-Path` mô tả references tới các artifact khác, không tự nhúng nội dung chúng vào JAR.
- Đặt file `dependency.jar` như một entry bên trong JAR thường **không tự** tạo classpath nested với Java launcher chuẩn.
- Với `java -jar`, thông tin application classpath đến từ cơ chế archive/manifest/launcher, không nên giả định `-cp` bên ngoài sẽ bổ sung theo cách như khi chạy main class trực tiếp.
- Spring Boot và các framework khác có thể dùng **launcher riêng** để đọc nested JAR.

### 3.3. `Implementation-Version` và metadata phát hành

Các thuộc tính như:

~~~text
Implementation-Title: Payment Service
Implementation-Version: 2.3.0
Implementation-Vendor: Example Corp
Build-Jdk-Spec: 21
~~~

có thể phục vụ nhận diện release hoặc các API `Package` trong phạm vi class loader phù hợp. Nhưng chúng **không chứng minh** class file tương thích với JDK đích. Một JAR ghi `Build-Jdk-Spec: 17` vẫn có thể chứa class của dependency yêu cầu Java 21 nếu pipeline đóng gói sai.

Nên lưu thêm artifact checksum, dependency lockfile và build provenance thay vì coi metadata text như kiểm chứng runtime.

### 3.4. Package sealing trong manifest

Manifest có thể khai báo sealing để hạn chế cách class thuộc một package được định nghĩa từ các code sources khác nhau.

Ví dụ sealing toàn archive:

~~~text
Manifest-Version: 1.0
Sealed: true

~~~

Hoặc section áp dụng cho package:

~~~text
Name: com/example/internal/
Sealed: true

~~~

Khi shade dependencies hoặc dùng nhiều JAR chứa cùng package, package sealing có thể tạo lỗi `SecurityException`. Cần xem cơ chế package definition và code source của các classes; đừng bỏ `Sealed` chỉ để làm lỗi biến mất khi chưa hiểu cam kết của thư viện.

## 4. `Automatic-Module-Name` và `module-info.class`

Trong Java 9 trở lên, JAR trên module path có thể là explicit module nếu chứa `module-info.class`, hoặc automatic module nếu không có descriptor mà được đặt trên module path theo các quy tắc JPMS.

### 4.1. Automatic module name ổn định

Tên automatic module có thể được suy từ tên file JAR. Khi thư viện đổi từ `library-1.0.jar` sang `library-core-2.0.jar`, tên suy ra có thể đổi, khiến consumer với `requires` cố định gặp lỗi.

Manifest có thể khai báo:

~~~text
Automatic-Module-Name: com.example.library.core
~~~

Đây là cách cung cấp tên ổn định cho thư viện chưa có explicit descriptor. Nếu repack làm mất thuộc tính đó, modular consumer có thể không tìm thấy module mong đợi.

### 4.2. Không đồng nhất manifest name với explicit descriptor

Một JAR có `module-info.class` là explicit named module theo descriptor. `Automatic-Module-Name` không thay thế các khai báo:

~~~java
module com.example.library {
    requires java.sql;
    exports com.example.library.api;
    uses com.example.spi.PaymentProvider;
}
~~~

Gộp nhiều JAR có descriptors bằng một lệnh shade không tạo ra một descriptor thống nhất và đúng. Nếu artifact cuối là một module thực sự, phải thiết kế lại requires/exports/opens/uses/provides có chủ đích; không thể chỉ giữ một trong nhiều `module-info.class`.

### 4.3. Kiểm tra descriptor cuối

~~~bash
jar --describe-module --file library.jar
~~~

Lệnh này giúp xem module identity/descriptor theo cách công cụ `jar` diễn giải. Với automatic module, output có thể cung cấp tên module và thông tin tương ứng. Khi chuyển classpath sang module path, phải test runtime thực sự, vì class loader, package access và service discovery có thể khác.

## 5. Multi-release JAR và metadata

Multi-release JAR có thể chứa base classes và các biến thể dành cho JDK mới hơn.

~~~text
runtime-support.jar
├── META-INF/MANIFEST.MF
├── com/example/runtime/PlatformSupport.class
└── META-INF/versions/
    ├── 11/com/example/runtime/PlatformSupport.class
    └── 17/com/example/runtime/PlatformSupport.class
~~~

Manifest cần:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

Trên JDK hỗ trợ MR-JAR, runtime có thể chọn phiên bản class tối ưu theo release đang chạy, theo quy tắc JAR spec.

### 5.1. Mất thuộc tính manifest

Nếu `META-INF/versions` còn nhưng `Multi-Release: true` bị ghi đè trong bước repack, artifact có thể không được xử lý như multi-release JAR. Hậu quả không nhất thiết là crash: một bản cài đặt trên JDK 17 có thể dùng implementation base thay vì implementation chuyên cho JDK 17.

### 5.2. Gộp versioned classes sai

Nếu tool đưa class ở `META-INF/versions/17` về base path, runtime cũ có thể cố nạp bytecode mới hơn và gặp `UnsupportedClassVersionError`. Nếu các entry trùng tên bị ghi đè, một bản JDK có thể nhận implementation không đúng.

Cần chạy regression tests trên các runtime mà artifact cam kết hỗ trợ, không chỉ JDK cao nhất.

### 5.3. Kiểm tra

~~~bash
jar --list --file runtime-support.jar
jar --describe-module --file runtime-support.jar
jdeps --multi-release 17 --summary runtime-support.jar
~~~

`jdeps` phân tích dependency tĩnh của class variant đã chọn theo công cụ; nó không thay thế việc test runtime và resource lookup.

## 6. Chữ ký JAR: manifest digest, `.SF` và signature block

Signed JAR có thể chứa:

~~~text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
~~~

Tùy thuật toán, signature block có thể dùng `.DSA`, `.EC` hoặc dạng được tài liệu JDK tương ứng hỗ trợ. Không nên hard-code giả định mọi signed JAR chỉ có `.RSA`.

### 6.1. Manifest digests

Một manifest signed JAR có thể chứa section cho entry cụ thể:

~~~text
Manifest-Version: 1.0

Name: com/example/api/PaymentClient.class
SHA-256-Digest: <base64 digest minh họa>

~~~

Dòng digest trên là mẫu về cấu trúc, không phải giá trị hợp lệ. Khi ký thật, `jarsigner` tạo metadata phù hợp với signed entries.

### 6.2. Signature file và signature block

`*.SF` chứa thông tin digest liên quan manifest hoặc những section manifest. Signature block như `*.RSA` chứa chữ ký mật mã và thường thông tin chứng chỉ theo cơ chế JAR signing. Cùng nhau, chúng hỗ trợ xác minh nội dung đã ký và danh tính signer theo chính sách trust.

Điều này **không** tự xác nhận rằng:

- Một dependency không có lỗ hổng bảo mật.
- Certificate chain đáng tin theo chính sách doanh nghiệp.
- Chứng chỉ chưa hết hạn hoặc thuật toán vẫn được cho phép.
- Class file chạy được trên mọi JDK.
- Artifact không phụ thuộc thư viện thiếu.

Chữ ký hợp lệ là một lớp của supply-chain integrity, không phải bằng chứng tổng quát về chất lượng phần mềm.

### 6.3. Xác minh bằng `jarsigner`

~~~bash
jarsigner -verify -verbose -certs library.jar
~~~

Khi cần xử lý chặt các warnings theo chính sách:

~~~bash
jarsigner -verify -strict -verbose -certs library.jar
~~~

Cần đọc đầy đủ output: trạng thái signature cryptographic verification, warnings về certificate, trust chain, timestamp và thuật toán. Tùy JDK, `-strict` có thể ảnh hưởng exit status khi tồn tại một số cảnh báo nghiêm trọng.

### 6.4. Xác minh khi đọc entry

Trong cơ chế JAR verification, một số kiểm tra xảy ra khi class/resource signed được đọc hoặc nạp. Vì vậy việc ứng dụng khởi động thành công không nhất thiết chứng minh mọi entry đã được kiểm tra.

Ví dụ provider chỉ nạp khi một workflow hiếm được gọi có thể khiến lỗi signature xuất hiện muộn. Hãy verify artifact và chạy integration tests thực sự nạp các thành phần quan trọng.

### 6.5. CRC không thay thế chữ ký

ZIP CRC có thể phát hiện hỏng dữ liệu, nhưng không cung cấp authentication của người ký. Mã băm một file JAR có thể phục vụ checksum, nhưng không thay thế đầy đủ JAR signing và trust chain. Không được coi `jar --list` chạy được là bằng chứng JAR còn chữ ký hợp lệ.

## 7. Vì sao shade/repack làm chữ ký nguồn không còn hợp lệ?

Giả sử một dependency signed JAR có class và digest tương ứng:

~~~text
vendor-lib.jar
  |- META-INF/MANIFEST.MF
  |- META-INF/VENDOR.SF
  |- META-INF/VENDOR.RSA
  |- org/vendor/Parser.class
~~~

Build shade thực hiện relocation:

~~~text
org.vendor.Parser
    ->
com.example.shadow.vendor.Parser
~~~

Vì class/resource và manifest metadata thay đổi, signature files lấy từ JAR nguồn không còn mô tả đúng artifact mới.

Nếu tool copy signature files cũ vào shaded JAR, runtime/verifier có thể báo:

~~~text
java.lang.SecurityException:
    Invalid signature file digest for Manifest main attributes
~~~

Hoặc:

~~~text
java.lang.SecurityException:
    SHA-256 digest error for org/vendor/Parser.class
~~~

Thông điệp cụ thể tùy JDK và artifact; ý nghĩa chung là signed content/manifest không còn khớp metadata chữ ký.

### 7.1. Không “merge” signature blocks của nhiều JAR

Hai dependency được ký riêng không có nghĩa ta có thể copy tất cả `META-INF/*.SF` và `*.RSA` của chúng vào một uber JAR rồi coi cả uber JAR được ký bởi hai vendor đó. Các signature files gắn với những entry/manifest theo quy tắc ký của artifact nguồn.

Khi thay đổi nội dung và tổ chức archive, phải xem artifact đầu ra là **artifact mới** với chính sách signing/provenance riêng.

### 7.2. Lỗi signer mismatch

Khi các class cùng package được load từ các signed/un-signed hoặc differently signed sources, có thể gặp:

~~~text
java.lang.SecurityException:
  class "com.example.shared.Helper"'s signer information
  does not match signer information of other classes
  in the same package
~~~

Điều này khác với digest mismatch. Cần kiểm tra split package, code source, signer identities và classpath order. Đừng xử lý bằng cách tự xóa mọi signature files mà chưa hiểu lý do tồn tại.

### 7.3. Không xóa chữ ký tùy tiện

Một số hướng dẫn Shade đề xuất loại:

~~~text
META-INF/*.SF
META-INF/*.RSA
META-INF/*.DSA
META-INF/*.EC
~~~

Điều này chỉ có thể phù hợp nếu **tổ chức có quyền tạo artifact mới**, không tuyên bố giữ chữ ký gốc, và có quy trình bảo đảm provenance/ký lại khi cần. Việc bỏ signatures làm mất khả năng xác minh signer của artifact nguồn ở định dạng JAR mới.

Không được sửa signed vendor artifact rồi phân phối như thể đó vẫn là bản signed nguyên gốc. Nếu chính sách yêu cầu giữ nguyên chữ ký vendor, lựa chọn phù hợp có thể là **không shade thư viện đó**, mà phân phối dưới dạng JAR riêng.

## 8. Ký artifact mới sau mọi bước biến đổi

Một pipeline có kiểm soát:

~~~text
Compile + dependencies
         |
         v
Shade / relocate / package
         |
         v
Merge manifest và service metadata
         |
         v
Finalize artifact
         |
         v
Sign bằng khóa phát hành được phép
         |
         v
jarsigner -verify
         |
         v
Publish immutable artifact + provenance
~~~

Ký lại tạo một **chữ ký mới cho artifact cuối**, không khôi phục chữ ký vendor đã mất.

### 8.1. Ví dụ `jarsigner`

~~~bash
jarsigner \
  -keystore release-keystore.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app-unsigned.jar \
  release-signer
~~~

Đây là cú pháp minh họa; cần có keystore và alias được cấp phép. Trong production, signing key/password phải được quản lý qua secret store, signing service hoặc pipeline bảo mật phù hợp, không đặt trong source repository hay CLI history không kiểm soát.

Sau đó:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

Nếu artifact bị sửa sau bước ký, cần ký lại theo đúng quy trình. Không coi `jarsigner -verify` là cách bỏ qua đánh giá lỗ hổng, provenance hoặc policy về chứng chỉ.

### 8.2. Reproducible builds và signing

Các yếu tố như timestamps, entry order và build metadata có thể làm checksum artifact khác nhau dù source gần giống. Nếu cần reproducible builds, thiết kế build determinism và signing step phù hợp, ghi versions và checksums. Nhưng **reproducibility** khác với **authenticity**: build tái lập được chưa tự chứng minh artifact đến từ người phát hành đáng tin.

## 9. `META-INF/services` và `ServiceLoader`

Java SPI cho phép tìm implementation mà client không cần import class cụ thể. Ví dụ interface:

~~~java
package com.example.spi;

public interface Compressor {
    String name();
    byte[] compress(byte[] data);
}
~~~

Một provider:

~~~java
package com.example.impl;

import com.example.spi.Compressor;

public final class FastCompressor implements Compressor {
    public FastCompressor() {}

    @Override
    public String name() {
        return "fast";
    }

    @Override
    public byte[] compress(byte[] data) {
        return data; // Ví dụ minh họa, chưa nén dữ liệu
    }
}
~~~

Một provider khác có thể nằm trong `org.vendor.impl.CompactCompressor`.

### 9.1. File service configuration

Tên file phải theo service interface:

~~~text
META-INF/services/com.example.spi.Compressor
~~~

JAR provider thứ nhất:

~~~text
com.example.impl.FastCompressor
~~~

JAR provider thứ hai có cùng đường dẫn file nhưng nội dung:

~~~text
org.vendor.impl.CompactCompressor
~~~

### 9.2. Client tìm providers

~~~java
package com.example.app;

import com.example.spi.Compressor;
import java.util.ServiceLoader;

public class DiscoverCompressors {
    public static void main(String[] args) {
        for (Compressor provider :
                ServiceLoader.load(Compressor.class)) {
            System.out.println(provider.name());
        }
    }
}
~~~

Trong môi trường classpath có đầy đủ provider JARs, client có thể nhận được hai providers. File `META-INF/services` có thể chứa comments với `#`, nhiều dòng tên class và không phải Java source file.

### 9.3. Khi trùng tên file bị overwrite

Nếu một task tạo uber JAR giữ chỉ service file của dependency thứ nhất, artifact cuối vẫn có:

~~~text
META-INF/services/com.example.spi.Compressor
  com.example.impl.FastCompressor
~~~

nhưng không còn `CompactCompressor`. Kết quả có thể không ném exception; chỉ có một provider bị thiếu. Đây là regression chức năng.

**Phải merge provider declarations**, không chọn một file trùng đường dẫn theo chiến lược tùy tiện.

### 9.4. Nội dung sau merge

~~~text
META-INF/services/com.example.spi.Compressor
  com.example.impl.FastCompressor
  org.vendor.impl.CompactCompressor
~~~

Trong file thực, các dòng là tên class, không có dấu thụt đầu dòng từ sơ đồ minh họa. Nếu ghép bytes mà file đầu không kết thúc bằng newline, hai tên provider có thể dính nhau và dẫn đến `ServiceConfigurationError`.

### 9.5. Provider có thể lỗi dù file tồn tại

`ServiceLoader` có thể thất bại nếu:

- Tên provider không còn tồn tại.
- Provider không implement đúng interface.
- Constructor/provider method không phù hợp với cơ chế được hỗ trợ.
- Class loader không nhìn thấy dependency.
- Static initializer hoặc constructor của provider ném exception.
- Module provider chưa resolve hoặc descriptor sai.
- Jar minimizer loại class chỉ được tham chiếu động.

Do đó kiểm thử cần instantiate và gọi một method an toàn của provider, không chỉ kiểm tra file có tồn tại.

## 10. Relocation và minimization ảnh hưởng metadata

### 10.1. Tên class bên trong service file cần được relocate

Nếu shade đổi:

~~~text
org.vendor.impl.CompactCompressor
   ->
com.example.shadow.vendor.CompactCompressor
~~~

thì nội dung service file cũng phải thay. Giữ tên cũ khiến `ServiceLoader` cố nạp class không còn ở vị trí đó:

~~~text
java.util.ServiceConfigurationError:
  com.example.spi.Compressor:
  Provider org.vendor.impl.CompactCompressor not found
~~~

Nếu chính service interface bị relocate, tên file `META-INF/services/<interface>` cũng cần tương ứng với tên mới. Một transformer phù hợp cần xử lý đồng bộ class names và service metadata.

### 10.2. Minimization có thể xóa provider

Mã client chỉ có tham chiếu tĩnh tới `Compressor.class`; `CompactCompressor` có thể chỉ xuất hiện dưới dạng tên text trong service file. Bộ tối ưu chỉ nhìn class references có thể loại provider class vì tưởng không dùng.

Lập sơ đồ:

~~~text
ServiceLoader.load(Compressor.class)
          |
          v
META-INF/services/com.example.spi.Compressor
          |
          v
org.vendor.impl.CompactCompressor
          |
          v
Class bị xóa bởi minimizer -> runtime error
~~~

Khi dùng `minimizeJar` hoặc tree-shaking, phải kiểm kê reflection, SPI, framework metadata, config class names và plugin entry points. Không nên khẳng định dependency không dùng chỉ vì `jdeps` hoặc static analyzer không thấy tham chiếu kiểu trực tiếp.

### 10.3. Provider từ framework

Ngoài Java SPI, nhiều framework có resource như:

~~~text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/native-image/...
META-INF/LICENSE
META-INF/NOTICE
~~~

`ServicesResourceTransformer` chỉ xử lý nhóm service descriptor thích hợp; nó không tự sửa mọi metadata của framework. Cần transformer theo từng định dạng và version framework. Không nên gộp các file license/notice bằng cách loại bỏ nội dung tùy ý.

## 11. Named modules: `uses` và `provides`

Trong JPMS, explicit named module có thể khai báo dịch vụ bằng descriptor.

Service API module:

~~~java
module com.example.spi.api {
    exports com.example.spi;
}
~~~

Provider module:

~~~java
module com.example.codec.fast {
    requires com.example.spi.api;
    provides com.example.spi.Compressor
        with com.example.impl.FastCompressor;
}
~~~

Consumer module:

~~~java
module com.example.app {
    requires com.example.spi.api;
    uses com.example.spi.Compressor;
}
~~~

### 11.1. Classpath SPI không tự thay explicit module descriptor

Khi dùng explicit named modules, `provides ... with ...` và `uses` là hợp đồng module quan trọng. Không thể chỉ copy file `META-INF/services` từ JAR classpath rồi coi nó tương đương hoàn toàn với module descriptor đã khai báo.

Automatic modules có cơ chế xử lý legacy service configuration riêng, nhưng vẫn phải xác minh trong module graph thực tế.

### 11.2. Module resolution và class loader

Một provider module có thể tồn tại trên disk nhưng chưa được resolve vào runtime module graph. Khi đó `ServiceLoader` không nhất thiết tìm thấy nó.

Chạy trong mô hình đúng:

~~~bash
java --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

Và kiểm tra provider:

~~~bash
jar --describe-module --file provider.jar
~~~

Với custom `ModuleLayer` hoặc class loader, cách gọi `ServiceLoader.load`/`load(layer, service)` cần phù hợp. Test chạy trên classpath không đủ để chứng minh JPMS service binding.

## 12. Maven Shade Plugin: gộp resources theo loại

`maven-shade-plugin` có các *resource transformers*. Những transformer thường dùng là:

- `ManifestResourceTransformer`: thiết lập manifest chính, ví dụ `Main-Class`.
- `ServicesResourceTransformer`: gộp service provider files và hỗ trợ xử lý các tên provider khi relocation.

Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.1</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <transformers>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.example.app.Main</mainClass>
                    </transformer>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer" />
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Khi dùng example trong dự án, pin plugin version thích hợp và kiểm tra Maven/Java compatibility. Cần thêm các transformer hoặc filters khác khi metadata thực tế đòi hỏi.

### 12.1. Manifest transformer không merge services

Việc khai `mainClass` chỉ xử lý entry point; không tự giữ các providers từ mọi dependencies. Ngược lại, services transformer không tự chọn main class đúng. Cần cấu hình riêng từng mục tiêu.

### 12.2. Filters với signature files phải có chính sách rõ

Một mẫu cấu hình thường thấy trong shaded JAR:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.RSA</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.EC</exclude>
        </excludes>
    </filter>
</filters>
~~~

Mẫu này chỉ phù hợp **khi có quyền tạo artifact mới và chính sách chấp nhận không giữ signatures nguồn**, hoặc artifact cuối sẽ được ký mới theo quy trình phát hành. Không nên dùng để “vượt qua lỗi chữ ký” trong hệ thống mà provenance/signatures của vendor là bắt buộc.

### 12.3. Đừng quên `minimizeJar` và dependency-reduced POM

Nếu sử dụng minimization, các class chỉ được nạp qua ServiceLoader/reflection có thể bị loại. Nếu tạo dependency-reduced POM, thông tin dependency của artifact được phát hành cũng có thể thay đổi. Cần kiểm tra cả runtime artifact và metadata phân phối trong repository.

### 12.4. Test shaded artifact

Unit tests có thể chạy từ `target/classes`, chưa qua bước shade. Cần chạy chính shaded artifact sau `package` bằng launcher thực, rồi kiểm tra providers và functions trong runtime.

## 13. Gradle Shadow Plugin

Với Gradle Shadow Plugin, có thể dùng `mergeServiceFiles()` để gộp các service descriptors và cấu hình manifest cho entry point.

Ví dụ Groovy DSL minh họa:

~~~groovy
plugins {
    id 'java'
    id 'com.gradleup.shadow' version '8.3.9'
}

tasks.named('shadowJar') {
    mergeServiceFiles()

    manifest {
        attributes('Main-Class': 'com.example.app.Main')
    }
}
~~~

Cú pháp và plugin ID/version có thể thay đổi theo nhánh Gradle/Shadow. Hãy đối chiếu tài liệu của version thực tế, không coi ví dụ là một template áp dụng cho mọi project.

### 13.1. `duplicatesStrategy` ảnh hưởng service merging

Nếu cấu hình duplicate handling loại những entry trùng tên **trước khi transformer nhận**, một số service providers có thể bị bỏ qua. Khi dịch vụ không đầy đủ, kiểm tra:

- `mergeServiceFiles()` có thực sự chạy không?
- `duplicatesStrategy` được cấu hình ở đâu?
- Có `exclude` resource nào không?
- Có relocation chưa cập nhật tên provider không?
- Có `minimize()` loại class động không?

Kiểm tra nội dung `META-INF/services` của JAR đầu ra, không chỉ nhìn build logs.

### 13.2. Reproducible builds

Repacking có thể thay entry order, timestamps và compression metadata làm checksum khác nhau. Cần cấu hình archive reproducibility nếu dự án có yêu cầu. Nhưng chữ ký, provenance và service correctness vẫn phải được xác minh độc lập.

## 14. Spring Boot executable JAR: nested dependencies và launcher

Một Spring Boot executable JAR thường không giống flat shaded JAR:

~~~text
app.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/app/Application.class
│   │   └── META-INF/services/...
│   └── lib/
│       ├── framework.jar
│       └── driver.jar
└── org/springframework/boot/loader/...
~~~

Bootstrap launcher của Spring Boot được thiết kế để nạp nested dependencies. Manifest có thể trỏ `Main-Class` tới Boot launcher, và giữ tên application entry point trong `Start-Class`.

Ví dụ mang tính khái niệm:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.app.Application
~~~

Tên class launcher có thể thay đổi giữa các bản Spring Boot. Nếu tự thay `Main-Class` bằng application class mà không có loader tương ứng, Java launcher chuẩn có thể không tìm được dependencies trong `BOOT-INF/lib`.

### 14.1. Signed nested JAR không có nghĩa signed outer JAR

Nếu một signed dependency được giữ **nguyên bytes** dưới dạng nested JAR, chữ ký nội bộ của dependency không tự bị thay bởi việc outer archive được đóng gói. Nhưng chữ ký đó không đồng nghĩa toàn bộ outer app.jar đã được ký/trusted.

Nếu task thực sự giải nén, relocate rồi gộp dependency, lại phải xử lý vấn đề invalidation như shaded JAR.

### 14.2. Test đúng cách chạy

~~~bash
java -jar app.jar
~~~

Đây là đường đi cần kiểm thử nếu production chạy Spring Boot executable archive. Chạy `java -cp target/classes:...` có thể dùng class loader/resource path khác và không phát hiện packaging regression.

## 15. Bảng lỗi phổ biến sau repack

| Triệu chứng | Hướng kiểm tra |
|---|---|
| `no main manifest attribute` | `MANIFEST.MF` trong artifact cuối thiếu `Main-Class` |
| `Could not find or load main class` | Class entry point, launcher, layout và JAR entries |
| `NoClassDefFoundError` sau `java -jar` | Manifest `Class-Path`, dependency locations, nested loader |
| `Invalid signature file digest` | Manifest/signed entries thay đổi nhưng còn signature metadata cũ |
| `SHA-256 digest error` | Entry đã ký không khớp digest |
| `signer information does not match` | Class cùng package có signer identities khác nhau |
| `ServiceConfigurationError: Provider ... not found` | Tên provider sai sau relocation hoặc class bị minimizer loại |
| `ServiceConfigurationError: ... not a subtype` | Provider không đúng SPI, duplicate class loader hoặc API version |
| Chỉ còn một provider | Các file `META-INF/services` bị overwrite thay vì merge |
| Module không tìm thấy | Mất `Automatic-Module-Name`, sai `module-info.class` hoặc module path |
| `ServiceLoader` rỗng trên module path | `uses`/`provides`, module graph, class loader/layer |
| MR-JAR mất implementation theo JDK | Mất `Multi-Release: true`, versioned class sai vị trí |
| Framework feature không kích hoạt | Resource metadata đặc thù framework bị ghi đè/loại |
| Test pass nhưng production fail | Unit tests không chạy artifact sau đóng gói |

### 15.1. Lỗi có thể chỉ xuất hiện muộn

Một provider chỉ được nạp khi người dùng bật một module ít dùng; signed resource có thể chỉ được xác minh khi chức năng đó truy cập. Vì vậy, việc healthcheck chạy xanh không đủ để tuyên bố artifact đã ổn.

### 15.2. Đừng chẩn đoán chỉ dựa trên exception class

`ClassNotFoundException` có thể do manifest, relocation, module resolution hoặc minimization. `SecurityException` có thể liên quan signature, package sealing hoặc signer mismatch. Cần đọc cause và kiểm tra artifact thực sự, không sửa theo một mẫu lỗi mà chưa xác nhận.

## 16. Các lệnh kiểm tra JAR sau đóng gói

### 16.1. Liệt kê entries

~~~bash
jar --list --file app.jar
~~~

Tìm:

~~~text
META-INF/MANIFEST.MF
META-INF/services/
META-INF/*.SF
META-INF/*.RSA
META-INF/*.DSA
META-INF/*.EC
module-info.class
META-INF/versions/
~~~

Trên shell Unix có thể lọc bằng `grep`; trên Windows PowerShell dùng `Select-String`. Liệt kê chỉ cho biết đường dẫn, không chứng minh nội dung bên trong đúng.

### 16.2. Đọc manifest

Nếu có `unzip`:

~~~bash
unzip -p app.jar META-INF/MANIFEST.MF
~~~

Nếu không có, có thể dùng `jar --extract` trong thư mục **tạm riêng** rồi đọc file manifest:

~~~bash
mkdir inspect-jar
cd inspect-jar
jar --extract --file ../app.jar META-INF/MANIFEST.MF
~~~

Các lệnh dùng ví dụ đường dẫn cho shell Unix. Chỉ trích xuất artifact đáng tin vào nơi phù hợp; không giải nén nội dung không đáng tin vào thư mục chứa dữ liệu quan trọng.

### 16.3. Xác minh chữ ký

~~~bash
jarsigner -verify -strict -verbose -certs app.jar
~~~

Đọc kết quả verify và warnings về signer, certificate chain, disabled algorithms. Nếu artifact theo chính sách không ký, cần ghi rõ điều đó thay vì giả định vendor signature vẫn tồn tại sau shade.

### 16.4. Xem service file

~~~bash
unzip -p app.jar META-INF/services/com.example.spi.Compressor
~~~

Đối chiếu nội dung với danh sách providers mong đợi. Nếu class names đã relocate, file phải phản ánh tên mới.

### 16.5. Xem module descriptor và multi-release

~~~bash
jar --describe-module --file app.jar
jdeps --multi-release 17 --summary app.jar
~~~

Các lệnh cung cấp bằng chứng tĩnh bổ sung, không thay integration test chạy artifact.

### 16.6. Khởi động artifact cuối

~~~bash
java -jar app.jar
~~~

Nếu mô hình là named module:

~~~bash
java --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Chọn đúng launcher mà production sử dụng. Một Spring Boot app cần nested loader không thể kiểm thử tương đương bằng main class path tùy ý.

## 17. Kiểm thử ServiceLoader trên artifact cuối

Một smoke test nên kiểm tra provider thực sự được instantiate và sử dụng.

~~~java
import com.example.spi.Compressor;
import java.util.HashSet;
import java.util.ServiceLoader;
import java.util.Set;

public final class ServiceSmokeTest {
    public static void main(String[] args) {
        Set<String> names = new HashSet<>();

        for (Compressor provider :
                ServiceLoader.load(Compressor.class)) {
            names.add(provider.name());
            byte[] output = provider.compress(new byte[] {1, 2, 3});

            if (output == null) {
                throw new AssertionError(
                    "Null result from " + provider.getClass());
            }
        }

        if (!names.contains("fast") ||
            !names.contains("compact")) {
            throw new AssertionError(
                "Missing provider(s): " + names);
        }

        System.out.println("Providers: " + names);
    }
}
~~~

Bài test này giả định deployment **phải có** hai providers. Với sản phẩm thật, danh sách mong đợi cần theo artifact/profile cụ thể. Không chỉ test metadata dạng text; cần đi qua class loading và method call thực tế.

Một ma trận có ích:

| Môi trường | Điều cần thử |
|---|---|
| Java classpath, dependencies tách riêng | Provider discovery trước repack |
| Flat shaded JAR | Provider discovery sau merge/relocation |
| Spring Boot executable JAR | Discovery qua nested JAR launcher |
| JPMS module path | `uses`/`provides` và module resolution |
| JDK tối thiểu hỗ trợ | Bytecode, MR-JAR base, providers |
| JDK mới | MR-JAR variants và API behavior |

Nếu provider không xuất hiện, phải xác định nó thiếu trong file, thiếu class, bị module resolution ẩn hay do class loader không đúng.

## 18. CI pipeline và signing policy

Một pipeline đáng tin có thể chia thành:

~~~text
Compile/test
      |
      v
Package/shade/repackage
      |
      v
Inspect artifact:
    manifest / module-info / MR-JAR
    META-INF/services / framework metadata
    signatures / licenses
      |
      v
Sign final artifact (nếu yêu cầu)
      |
      v
Verify signing + trust policy
      |
      v
Run black-box launch test
      |
      v
Run ServiceLoader/framework integration tests
      |
      v
Publish immutable artifact + checksum/SBOM
~~~

### 18.1. Tách unit tests và packaging tests

Unit tests thường chạy bằng Maven/Gradle test runtime classpath. Packaging tests phải kiểm tra file được phát hành. Với Maven Shade có thể có `original-...jar` và shaded JAR; với Spring Boot plugin có thể có artifact đã repack khác JAR gốc. Phải chỉ đúng artifact cuối cùng.

### 18.2. Kiểm soát provenance

Nếu có signed dependencies, nên ghi được nguồn, phiên bản, checksum và license của chúng. Khi tạo artifact mới, không tuyên bố chữ ký của các dependency gốc đang bảo đảm toàn bộ shaded artifact. Một SBOM/lockfile giúp lưu dấu các thành phần nguồn, nhưng không tự thay thế ký artifact hoặc kiểm tra runtime.

### 18.3. Không sửa artifact sau signing

Một bước “inject configuration” vào JAR đã ký sau cùng có thể làm signature không hợp lệ. Nên giữ cấu hình môi trường ngoài artifact hoặc hoàn tất mọi biến đổi **trước bước ký**. Nếu quy trình buộc thay signed entry, phải ký lại theo chính sách phát hành và phát hành hash mới.

### 18.4. Rollback packaging cũng cần điều kiện

Nếu phiên bản mới đổi artifact layout, launcher, JPMS name hoặc plugin discovery, việc rollback về binary cũ đòi runtime, configuration và các dữ liệu do phiên bản mới tạo ra vẫn tương thích. Rollback JAR không tự đảo database, event schema hoặc service metadata của môi trường bên ngoài.

## 19. Những điều cần chú ý khi nâng JDK

### 19.1. JDK mới có thể siết chính sách thuật toán/chữ ký

Một JAR ký bằng thuật toán yếu có thể tạo cảnh báo hoặc bị xử lý khác ở JDK mới theo security policy. Cần kiểm tra tài liệu JDK đích và signer/certificate thực tế. Không tự hạ toàn bộ chính sách bảo mật chỉ để giữ một dependency quá cũ; ưu tiên bản cập nhật từ nguồn phát hành đáng tin.

### 19.2. Java 9+ thay đổi mô hình modularization

Một JAR chạy được trên classpath chưa chắc giữ nguyên hành vi trên module path. Service provider registration, exports/opens và module resolution là hợp đồng mới. Nếu repack làm mất module name hoặc descriptor, lỗi không nằm ở source `ServiceLoader`.

### 19.3. Build tool upgrade có thể đổi duplicate handling

Nâng Gradle/Maven plugin trong cùng migration có thể làm chính sách merge resources, timestamps hoặc exclusions thay đổi. Nếu service providers biến mất, so sánh JAR trước/sau và test cùng artifact trên hai JDK nếu có thể để xác định lỗi do **artifact biến đổi** hay do **runtime JDK**.

### 19.4. Java version của compiler không quyết định toàn bộ artifact

Một JAR có main class target Java 17 vẫn có thể chứa provider class target Java 21. Nếu provider chỉ được nạp ở một nhánh ít dùng trên Java 17, lỗi có thể xuất hiện muộn. Kiểm tra class file versions của **mọi runtime dependency/variant**, không chỉ class chính.

### 19.5. Native-image metadata là một hợp đồng khác

Với GraalVM Native Image, reflection/services/resources có những yêu cầu build-time riêng. Một JAR chạy tốt trên HotSpot chưa chắc có đủ metadata cho native-image build. Khi sử dụng plugin native image, cần kiểm tra cấu hình của framework/GraalVM ở phiên bản cụ thể.

## 20. Những hiểu nhầm phổ biến

**“JAR chỉ là ZIP chứa class files.”** Không đầy đủ. Manifest, signatures, module descriptor và service metadata có thể quyết định runtime behavior.

**“Có `Main-Class` trong POM nghĩa artifact cuối có `Main-Class`.”** Không chắc; task repack/shade cuối có thể ghi manifest khác.

**“Manifest `Class-Path` tự hỗ trợ nested JAR.”** Không. Nested libraries cần class loader/launcher được thiết kế cho layout đó.

**“`Automatic-Module-Name` thay thế toàn bộ `module-info.class`.”** Không. Nó chủ yếu đặt tên automatic module; explicit module descriptor có hợp đồng khác.

**“Giữ thư mục `META-INF/versions` là đủ cho MR-JAR.”** Không; cần `Multi-Release: true` và cấu trúc class theo spec.

**“Chữ ký JAR nguồn vẫn hợp lệ sau khi relocation.”** Không nếu signed contents/manifest bị biến đổi theo cách phá digest.

**“Cứ xóa `*.SF` và `*.RSA` là sửa xong.”** Không. Việc này thay đổi integrity/provenance; chỉ phù hợp với chính sách phát hành artifact mới được cho phép.

**“`jarsigner -verify` thành công nghĩa không có lỗi bảo mật.”** Không. Ký xác nhận integrity/authenticity theo trust model, không phải vulnerability scan.

**“Một service interface chỉ có một provider.”** Không. Nhiều JAR có thể cung cấp providers; file service trùng tên phải được merge đúng.

**“Service file đã có nên provider luôn hoạt động.”** Không. Provider class có thể bị xóa, relocate sai, thiếu constructor hoặc bị module/classloader chặn.

**“Maven Shade ServicesResourceTransformer xử lý mọi resource của Spring.”** Không. Metadata riêng framework có transformer/merge policy riêng.

**“Unit test từ `target/classes` chứng minh shaded JAR chạy được.”** Không. Cần kiểm thử artifact cuối với launcher thật.

## 21. Checklist phát hành

- [ ] Đã xác định đúng artifact sẽ deploy, checksum và plugin versions.
- [ ] Đã liệt kê entries của JAR cuối bằng `jar --list`.
- [ ] Đã đọc `META-INF/MANIFEST.MF` thực tế và xác nhận `Main-Class`/launcher.
- [ ] Đã kiểm tra `Class-Path` và cách phân phối dependencies.
- [ ] Đã xem `Automatic-Module-Name`, `module-info.class` và module path strategy.
- [ ] Nếu có MR-JAR, đã giữ `Multi-Release: true` và test trên các JDK hỗ trợ.
- [ ] Đã xem sealing/digest sections trong manifest nếu có.
- [ ] Đã xác định signed dependencies và chính sách provenance.
- [ ] Đã tránh giữ stale signatures sau khi biến đổi signed entries.
- [ ] Nếu final artifact cần ký, đã ký **sau** package/shade và verify.
- [ ] Đã merge đúng các file `META-INF/services` trùng tên.
- [ ] Đã cập nhật provider/service names sau relocation.
- [ ] Đã kiểm tra minimization không xóa class chỉ được gọi động.
- [ ] Đã giữ metadata framework, license và notice cần thiết.
- [ ] Đã chạy black-box `java -jar`/`java --module` trên artifact cuối.
- [ ] Đã chạy integration test cho ServiceLoader và chức năng provider.
- [ ] Đã kiểm tra class file version của provider/dependency trên JDK tối thiểu.
- [ ] Đã có CI gate cho manifest, signing, module và service metadata.
- [ ] Đã lưu checksum, SBOM/provenance và release notes.
- [ ] Đã xác định rollback strategy nếu thay layout/module/launcher.

## 22. Nguồn tài liệu kỹ thuật

- [JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest, JAR signing và multi-release JAR.
- [`jar` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): tạo, trích xuất, liệt kê và mô tả module JAR.
- [`jarsigner` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): ký và xác minh artifact.
- [`ServiceLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service provider configuration và named modules.
- [Maven Shade Plugin – Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html): manifest và service resource transformers.
- [Gradle Shadow – Merging Service Descriptor Files](https://gradleup.com/shadow/configuration/merging/#merging-service-descriptor-files): gộp provider metadata.
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): executable archive và nested JAR launcher.
- [JEP 238 – Multi-Release JAR Files](https://openjdk.org/jeps/238): mục tiêu và quy tắc MR-JAR.

Cần đối chiếu hướng dẫn của **đúng phiên bản JDK, plugin, framework** mà dự án triển khai. Đường dẫn launcher, Gradle DSL, cách merge mặc định và chính sách thuật toán ký có thể thay đổi theo các bản phát hành.

## 23. Kết luận

**Đóng gói lại JAR là một thay đổi runtime contract**, không chỉ là nén lại bytecode. `MANIFEST.MF` điều khiển nhiều thông tin launcher/module/MR-JAR; chữ ký JAR gắn với signed entries và không được coi là còn hiệu lực khi artifact bị biến đổi; `META-INF/services` quyết định những providers mà `ServiceLoader` có thể tìm thấy. Từng loại metadata cần được xử lý theo cơ chế và chính sách phù hợp.

Để Java Advance Compatibility Migration an toàn, hãy tạo artifact theo một layout rõ ràng, merge service registrations khi shade, giữ các manifest properties cần thiết, không giả vờ bảo toàn chữ ký vendor sau khi đổi nội dung và ký artifact cuối nếu chính sách yêu cầu. **Chỉ kiểm chứng source/compile là chưa đủ: phải đọc và chạy chính JAR sẽ phát hành trên JDK mục tiêu**, xác minh chữ ký, module/service metadata và các chức năng dùng resource động.
