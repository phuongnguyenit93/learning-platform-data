# Giới hạn API công khai và kiểm thử từng nhánh của multi-release JAR

## 1. Bài toán: một thư viện, nhiều phiên bản Java

Một thư viện Java có thể cần tiếp tục phục vụ ứng dụng chạy Java 8, đồng thời muốn khai thác các API và cơ chế tối ưu có trong Java 17 hoặc Java 21. Nếu buộc tất cả consumer nâng Java ngay lập tức, nhà phát triển thư viện có thể phá hợp đồng hỗ trợ. Nếu chỉ viết code theo Java 8, thư viện lại khó tận dụng những tính năng runtime mới.

**Multi-release JAR (MRJAR)** giải quyết một phần bài toán này: một file JAR chứa lớp triển khai cơ sở và các biến thể dành cho từng mức Java. JVM chọn lớp phù hợp nhất với release đang chạy, trong khi **API công khai của thư viện phải được giữ nhất quán qua các nhánh** theo JAR File Specification.

Điểm nguy hiểm là cùng tên class nhưng mã bytecode thực thi trên Java 8 có thể khác mã chạy trên Java 17 hoặc 21. Một unit test chạy thành công trên JDK hiện tại chưa chứng minh:

- Nhánh **base** còn chạy trên Java tối thiểu đã công bố.
- Nhánh **17** không vô tình thêm method public chỉ có ở Java 17.
- Nhánh **21** không làm thay đổi hành vi, security checks hoặc dữ liệu serialized.
- Runtime **11** thực sự dùng base hay một nhánh trung gian như dự kiến.
- Tool phân tích dependency, coverage, shading, signing và module packaging đều hiểu MRJAR.
- Consumer đã compile với một nhánh có thể liên kết được khi chạy trên nhánh khác.

Bài học này tập trung vào hai việc trong **Java Advance Compatibility Migration — Đóng gói và môi trường**:

1. Hiểu **giới hạn của API công khai** khi tạo những class trùng tên ở `META-INF/versions/N`.
2. Xây **ma trận build, kiểm tra artifact và chạy test trên từng nhánh** để chứng minh một JAR hỗ trợ đúng những JDK đã cam kết.

## 2. Multi-release JAR là gì, và không phải là gì?

JEP 238 đưa multi-release JAR vào nền tảng từ Java 9. Một JAR có thể chứa:

~~~text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/lib/Feature.class
│       ├── 17/
│       │   └── com/example/lib/Feature.class
│       └── 21/
│           └── com/example/lib/Feature.class
└── com/example/lib/Feature.class
~~~

Manifest ở **main section** cần có:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Khi cơ chế MRJAR được dùng, một runtime Java đủ mới ưu tiên versioned entries thích hợp thay vì chỉ đọc class ở root.

**MRJAR không phải:**

- Một công cụ để phát hành **API v1/v2/v3 khác nhau** trong cùng JAR tùy Java runtime.
- Một dạng Maven classifier hay nhiều release artifact được tự chọn bởi dependency resolver.
- Một tính năng cho phép chạy bytecode Java 21 trên Java 8 chỉ nhờ đổi đường dẫn trong JAR.
- Một bộ kiểm thử tương thích tự động.
- Một cơ chế tự động giữ backward/forward behavioral compatibility.
- Một thay thế cho việc version hóa thư viện bằng semantic/API versioning.

Ý tưởng chính là **cùng hợp đồng thư viện, nhiều implementation theo runtime**, không phải “cùng tọa độ dependency nhưng public interface thay đổi tùy máy”.

## 3. Cấu trúc thư mục và quy tắc nhận diện

Một MRJAR hợp lệ sử dụng đường dẫn:

~~~text
META-INF/versions/N/<relative-entry-path>
~~~

với `N` là một số phiên bản Java release hợp lệ và **`N >= 9`**.

Ví dụ:

~~~text
com/example/Codec.class
META-INF/versions/11/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
META-INF/versions/21/com/example/Codec.class
~~~

Không có nhánh đặc biệt `META-INF/versions/8` dành cho Java 8. Code cho Java 8, hoặc mức tối thiểu thấp hơn nếu được hỗ trợ, đặt ở **root**.

### 3.1. Manifest là điều kiện cần

Nếu thiếu `Multi-Release: true` hoặc giá trị không được nhận là `true`, việc có directory `META-INF/versions` không tự khiến class loader chọn những bản thay thế. Đặc tả manifest chấp nhận giá trị `true` không phân biệt chữ hoa/chữ thường, nhưng nên viết đúng dạng chuẩn để dễ review.

Không nên trông đợi việc copy các class files vào `META-INF/versions` mà quên manifest sẽ tự hoạt động.

### 3.2. Giới hạn class-file version

Class nằm trong nhánh `N` phải có class-file major version **không cao hơn** mức bytecode tương ứng với Java `N`. Ví dụ:

| Vị trí | Mức Java tối đa trong nhánh | Class-file major tối đa |
| --- | ---: | ---: |
| Root — thư viện cam kết Java 8 | Java 8 | 52 |
| `META-INF/versions/9` | Java 9 | 53 |
| `META-INF/versions/11` | Java 11 | 55 |
| `META-INF/versions/17` | Java 17 | 61 |
| `META-INF/versions/21` | Java 21 | 65 |

Không được đặt class compile bằng Java 21 mặc định (major 65) vào directory `versions/17` rồi hy vọng runtime Java 17 chấp nhận. Tên thư mục không biến đổi bytecode.

### 3.3. Không phải mọi mục trong `META-INF` đều được version hóa

JAR File Specification nêu rõ **resources nằm dưới `META-INF` không được version hóa theo cơ chế MRJAR**, chẳng hạn `META-INF/services/...`. Không đặt những ServiceLoader provider configuration files trong `META-INF/versions/17/META-INF/services` rồi kỳ vọng ServiceLoader tự chọn theo JDK.

Với module descriptors, có các quy tắc đặc thù khi đặt `module-info.class` trong nhánh versioned; xem phần JPMS ở dưới.

## 4. JVM chọn nhánh nào?

Giả sử JAR chứa root, nhánh 9, 17 và 21:

~~~text
Root:     Feature.class  (Java 8 compatible)
Version9: Feature.class  (Java 9)
Version17:Feature.class  (Java 17)
Version21:Feature.class  (Java 21)
~~~

Khi runtime hỗ trợ MRJAR và dùng cơ chế class loading phù hợp, JVM tìm theo release hiện tại từ cao xuống thấp:

| JVM thực thi | Thứ tự ưu tiên xét khi nạp `Feature` | Kết quả nếu có đủ như ví dụ |
| --- | --- | --- |
| Java 8 | Chỉ root | Root |
| Java 9 | 9 → root | Nhánh 9 |
| Java 11 | 11 → 10 → 9 → root | Nhánh 9 |
| Java 17 | 17 → … → 9 → root | Nhánh 17 |
| Java 19 | 19 → 18 → 17 → … → root | Nhánh 17 |
| Java 21 | 21 → 20 → 19 → … → root | Nhánh 21 |
| Java 23 | 23 → 22 → 21 → … → root | Nhánh 21 |

**Nhánh gần nhất không vượt quá runtime** được chọn; không nhất thiết trùng chính xác số release hiện tại.

### 4.1. Việc chọn xảy ra theo từng entry/class

Giả sử nhánh 21 chỉ có `FastCodec.class`, còn `CodecConfig.class` chỉ xuất hiện trong root. Trên Java 21, JVM có thể dùng:

~~~text
FastCodec.class   -> META-INF/versions/21/...
CodecConfig.class -> root/...
~~~

Đừng nghĩ runtime luôn chọn **một directory duy nhất** rồi bỏ toàn bộ directory khác. Quy tắc fallback áp dụng theo tên entry, trong phạm vi class loader/JAR access có hỗ trợ MRJAR.

### 4.2. Cảnh giác với custom class loader

Class loaders chuẩn và tooling nhận biết MRJAR theo đặc tả. Nhưng một custom loader tự đọc JAR như ZIP rồi định nghĩa class từ bytes của root có thể bỏ qua versioned entries. Với fat JAR launcher, plugin framework, nested-JAR loader hoặc classpath scanner riêng, phải kiểm chứng implementation có hỗ trợ MRJAR hay không.

Không lấy một test chạy bằng `java -cp library.jar` rồi mặc nhiên kết luận cơ chế loader tùy chỉnh trong application server cũng xử lý MRJAR giống hệt.

## 5. Giới hạn quan trọng nhất: public API phải giống nhau

JAR File Specification yêu cầu **public API được export bởi các class trong MRJAR phải giống nhau qua các phiên bản**. Đó là lý do cùng một class công khai trong nhánh Java 17 vẫn cần tồn tại trong root với cùng fully qualified name và access modifier, trừ ngoại lệ được đặc tả cho một số non-exported packages trong modular MRJAR.

Ví dụ không nên làm:

~~~java
// Root -- Java 8
package example.api;

public class PriceCalculator {
    public long total(long price, int quantity) {
        return price * quantity;
    }
}
~~~

~~~java
// META-INF/versions/17 -- KHÔNG ĐÚNG HỢP ĐỒNG PUBLIC API
package example.api;

public class PriceCalculator {
    public java.math.BigDecimal total(
            java.math.BigDecimal price, int quantity) {
        return price.multiply(
                java.math.BigDecimal.valueOf(quantity));
    }
}
~~~

Hai class cùng tên nhưng method public có descriptor khác: caller biên dịch với một nhánh có thể không liên kết được khi chạy với nhánh kia.

Mô hình đúng hơn:

~~~java
// Root và mọi nhánh thay thế đều giữ:
public long total(long price, int quantity)
~~~

nhưng **implementation bên trong** được phép dùng những APIs/thuật toán khác theo JDK.

### 5.1. Public API không chỉ là danh sách tên method

Các thành phần cần xem xét gồm:

- Fully qualified class name và tính hiển thị.
- Public/protected constructors.
- Public/protected methods, static/instance, return type và parameter types.
- Public/protected fields, kiểu field và modifiers.
- Superclass/interfaces và sự tương thích kiểu.
- API chịu ảnh hưởng generics/signatures, exceptions, annotations hoặc inheritance.
- Nested classes/interfaces/enums/records nếu chúng là một phần hợp đồng công khai.
- Method/field behavior mà consumer dựa vào, dù bytecode signature không đổi.

**Binary API**, **source API** và **behavioral contract** liên quan nhưng không đồng nhất. Ví dụ đổi generic signature có thể vẫn giữ erasure descriptor nhưng làm consumer recompile lỗi; đổi exception policy có thể phá ứng dụng mà method descriptor không đổi.

### 5.2. Method return type là một phần của JVM descriptor

Trong bytecode, `calculate(long)long` có descriptor `(J)J`; đổi sang `calculate(long)java.math.BigDecimal` tạo descriptor khác. Kể cả method name và tham số không đổi, Java caller đã compile với descriptor cũ có thể gặp `NoSuchMethodError`.

Vì vậy, khi kiểm tra public API, không chỉ so method names bằng text search. Hãy so descriptors/signatures đã compile và thử consumer thật.

## 6. Public API “giống nhau” không có nghĩa bytecode phải giống nhau

MRJAR tồn tại chính để implementation khác nhau. Ví dụ cùng một public method:

~~~java
public static String encode(byte[] bytes)
~~~

Nhánh Java 8 có thể tự chuyển bytes sang hex bằng vòng lặp. Nhánh Java 17 có thể dùng `java.util.HexFormat`. API public hoàn toàn giống nhau.

Những thay đổi thường thích hợp trong versioned implementation:

- Dùng Java SE API chỉ có ở JDK mới **bên trong** method.
- Dùng thuật toán tối ưu hơn hoặc concurrency primitives mới.
- Sử dụng class helper package-private riêng của nhánh khi quy tắc packaging cho phép.
- Giảm chi phí allocation hoặc thay implementation chi tiết nội bộ.
- Tối ưu cách đọc file, hash, buffer hoặc xử lý dữ liệu nếu behavior vẫn đúng.

Điều kiện: cách sử dụng từ phía consumer **không được đòi một Java public API khác nhau theo runtime**.

### 6.1. API công khai ổn định nhưng behavior cũng phải được kiểm thử

Hai nhánh có thể cùng trả `String` nhưng một nhánh sinh lowercase hex và nhánh kia uppercase hex. API signature không đổi, song kết quả khác:

~~~text
Java 8:  0a1b...
Java 17: 0A1B...
~~~

Đối với hashing, token, protocol headers, JSON serialization hoặc cache keys, khác biệt đó có thể phá hệ thống. Vì vậy **API parity check không thay behavioral compatibility tests**.

## 7. Những khác biệt API không nên đưa vào nhánh

| Thay đổi trong nhánh cao hơn | Rủi ro |
| --- | --- |
| Thêm public method chỉ ở nhánh 21 | Consumer compile trên 21 nhưng chạy 17 có thể `NoSuchMethodError` |
| Xóa/đổi tên public method ở nhánh 17 | Consumer biên dịch với root có thể lỗi liên kết |
| Đổi parameter/return type | Thay JVM method descriptor |
| Đổi instance method thành static | `IncompatibleClassChangeError` hoặc lỗi liên kết liên quan |
| Đổi public field type hoặc bỏ field | `NoSuchFieldError` hoặc ABI mismatch |
| Đổi public class thành interface hoặc ngược lại | Type/linkage incompatibility |
| Chuyển constructor public thành private | Consumer tạo instance có thể lỗi |
| Thêm public class chỉ ở nhánh cao (non-modular JAR) | Trái ràng buộc exported API/counterpart trong root |
| Đổi superclass/interfaces làm thay type relation | Có thể phá assignability/linkage |
| Đổi generic signature/annotation API | Có thể phá source/reflection/tooling dù JVM descriptor giữ nguyên |

Nếu thực sự cần phát hành một API mới, hãy **nâng phiên bản thư viện/API artifact** với compatibility policy rõ ràng, hoặc tạo artifact riêng theo runtime, thay vì giấu API mới trong nhánh MRJAR.

## 8. Những ngoại lệ và vùng nội bộ cần hiểu chính xác

Đặc tả phân biệt public/protected classes nằm ở exported API với các class nội bộ.

### 8.1. Package-private helpers

Một helper không public có thể chỉ tồn tại ở nhánh 17 để triển khai tối ưu:

~~~text
Root:
  example/api/Codec.class

META-INF/versions/17:
  example/api/Codec.class
  example/api/Hex17Support.class  (package-private)
~~~

`Codec` công khai phải giữ hợp đồng API, còn `Hex17Support` là chi tiết internal. Tuy nhiên tên, visibility và class dependencies vẫn cần tuân thủ quy tắc MRJAR và module boundaries; không nên dùng class ở nhánh cao làm kiểu trả về public của `Codec`.

### 8.2. Modular JAR và non-exported packages

Đối với **modular multi-release JAR**, đặc tả có ngoại lệ: public/protected class trong **package không được export** không nhất thiết phải có class counterpart cùng tên và access ở root. Lý do là package đó không thuộc public API được module export.

Đây không phải giấy phép để thay đổi tùy ý API của **exported package**. Nếu module descriptor export `example.api`, class trong `example.api` vẫn cần tuân thủ API parity.

Không nên dựa vào ngoại lệ này khi cùng JAR còn được dùng trên classpath và kỳ vọng tính đóng gói tương đương JPMS. Classpath và module path có cách điều khiển accessibility khác nhau.

### 8.3. Internal không đồng nghĩa không có ảnh hưởng

Một class package-private đổi behavior vẫn có thể làm public method trả kết quả khác. Reflection, serialization, ServiceLoader, logging và các framework scanning cũng có thể quan sát nội bộ. Do đó mức “không public” chỉ làm giảm ràng buộc API, không tự làm thay đổi trở nên không rủi ro.

## 9. Ví dụ xuyên suốt: thư viện SHA-256 hex hỗ trợ Java 8 và 17

Ta muốn phát hành một JAR:

- **Root** compile cho Java 8 để mọi consumer cũ dùng được.
- **Nhánh 17** sử dụng `HexFormat` có trong Java 17.
- Cả hai nhánh cung cấp **chính xác cùng public API**.
- Output sha256 hex luôn là lowercase, bất kể runtime.

Cấu trúc source:

~~~text
src/
├── main/
│   └── java/
│       └── example/crypto/HexDigest.java
└── java17/
    └── java/
        └── example/crypto/HexDigest.java
~~~

Hai file có cùng fully qualified class name nhưng **nằm ở source sets khác nhau**. Không compile cả hai như hai class trùng tên trong cùng một compilation unit/source set.

### 9.1. Root implementation dành cho Java 8

File `src/main/java/example/crypto/HexDigest.java`:

~~~java
package example.crypto;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class HexDigest {
    private static final char[] HEX =
            "0123456789abcdef".toCharArray();

    private HexDigest() {
    }

    public static String sha256Hex(byte[] input) {
        try {
            byte[] digest =
                    MessageDigest.getInstance("SHA-256").digest(input);
            char[] output = new char[digest.length * 2];

            for (int i = 0; i < digest.length; i++) {
                int unsigned = digest[i] & 0xff;
                output[2 * i] = HEX[unsigned >>> 4];
                output[2 * i + 1] = HEX[unsigned & 0x0f];
            }

            return new String(output);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

Tại thời điểm biên dịch root, dùng Java compiler có `--release 8` hoặc một pipeline compiler/bootclasspath được hỗ trợ để đảm bảo API Java 8. Ví dụ dùng JDK có hỗ trợ tùy chọn tương ứng:

~~~bash
javac --release 8 \
  -d build/classes/base \
  src/main/java/example/crypto/HexDigest.java
~~~

### 9.2. Implementation dành cho Java 17+

File `src/java17/java/example/crypto/HexDigest.java`:

~~~java
package example.crypto;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class HexDigest {
    private HexDigest() {
    }

    public static String sha256Hex(byte[] input) {
        try {
            byte[] digest =
                    MessageDigest.getInstance("SHA-256").digest(input);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

`HexFormat` là một API có trong Java 17, vì vậy đoạn code không thuộc root nếu thư viện phải hỗ trợ Java 8. Compile nhánh riêng:

~~~bash
javac --release 17 \
  -d build/classes/java17 \
  src/java17/java/example/crypto/HexDigest.java
~~~

**So sánh API:** Cả hai class đều là `public final`, có private constructor và một public static method `sha256Hex(byte[]):String`. Chúng khác chi tiết implementation và private fields, điều đó đúng với mục đích MRJAR.

### 9.3. Đóng gói bằng `jar`

Ví dụ các lệnh tương thích với JDK tool hỗ trợ `--release` trong `jar`:

~~~bash
jar --create \
  --file build/hex-digest.jar \
  -C build/classes/base .

jar --update \
  --file build/hex-digest.jar \
  --release 17 \
  -C build/classes/java17 .
~~~

`jar --release 17` đặt các entry đi sau vào `META-INF/versions/17` và hỗ trợ tạo MRJAR. Khi xây artifact thật cần xác nhận `Multi-Release: true` có trong manifest và kiểm tra danh sách entries, vì tùy pipeline packaging, shading hoặc custom build có thể ghi đè manifest.

Lệnh kiểm tra:

~~~bash
jar --list --file build/hex-digest.jar
jar --validate --file build/hex-digest.jar
~~~

JAR dự kiến có:

~~~text
META-INF/MANIFEST.MF
example/crypto/HexDigest.class
META-INF/versions/17/example/crypto/HexDigest.class
~~~

Đây là ví dụ minh họa cách xây tối thiểu; build production nên dùng plugin/task có dependency rõ, quản lý toolchain và tái lập artifact.

## 10. Kiểm thử kết quả với một consumer độc lập

Consumer sử dụng public API duy nhất:

~~~java
package example.consumer;

import example.crypto.HexDigest;
import java.nio.charset.StandardCharsets;

public final class Main {
    public static void main(String[] args) {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        System.out.println(HexDigest.sha256Hex(bytes));
    }
}
~~~

Kết quả mong đợi:

~~~text
2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
~~~

Compile consumer theo Java 8 để khẳng định root API khả dụng:

~~~bash
javac --release 8 \
  -cp build/hex-digest.jar \
  -d build/consumer-classes \
  src/consumer/java/example/consumer/Main.java
~~~

Chạy cùng consumer bytecode với các JVM runtime đã cam kết hỗ trợ:

~~~bash
java -cp build/hex-digest.jar:build/consumer-classes \
  example.consumer.Main
~~~

Trên Windows, classpath separator thông thường là `;` thay cho `:`. Những lệnh trên là **kịch bản thực hành**, không phải lệnh đã chạy cho bài học này.

### 10.1. Output giống nhau chưa đủ chứng minh đúng nhánh

Hai implementations cố ý cho kết quả giống nhau. Muốn chứng minh runtime thật sự chọn nhánh, có thể:

- Xem code của mỗi variant bằng `javap --multi-release`.
- Dùng công cụ class-load diagnostics/JAR resource inspection phù hợp.
- Kiểm tra implementation-specific dependencies của classfile đã đóng gói.
- Thử một kịch bản đối chứng có instrument/debug markers trong môi trường test được kiểm soát, nhưng không phá public API.

Không đổi public method thành `implementationVersion()` chỉ có trong nhánh cao để “dễ test”: chính hành động đó làm lệch API. Nếu cần một method chẩn đoán public, nó cũng phải có cùng chữ ký ở root và mọi nhánh.

## 11. Chỉ biên dịch base một lần và từng nhánh một lần

Một pipeline đúng thường tách rõ:

~~~text
compileBase (--release 8)
      |
      +----> classes/base/

compile17 (--release 17)
      |
      +----> classes/java17/

packageMultiReleaseJar
      |
      +----> hex-digest.jar
             root/...
             META-INF/versions/17/...
~~~

**Không trộn output folders trước khi packaging.** Nếu copy classes của Java 17 đè lên root, JAR có thể không còn hỗ trợ Java 8 dù manifest nói là multi-release.

### 11.1. Dependency hướng từ nhánh cao tới base

Nhánh 17 có thể dùng API được công bố ở root và các class Java 17; root **không được** phụ thuộc trực tiếp vào những class chỉ tồn tại ở nhánh 17 hoặc API Java 17. Nếu root có bytecode tham chiếu class mới và chạy trên Java 8, class loading/linkage có thể thất bại.

Khi compile nhánh cao, việc có base output trên classpath có thể hữu ích cho những shared classes. Nhưng phải tránh nhầm lấy class đã compile của nhánh cao làm dependency ngược lại cho root.

### 11.2. Dùng `--release` thay vì chỉ `-source`/`-target`

Nếu compiler JDK 21 compile root với `-source 8 -target 8`, code có thể vô tình gọi JDK API mới mà compiler nhìn thấy trên platform hiện tại. `javac --release 8` hạn chế platform API theo release 8 và tạo bytecode phù hợp.

Tuy nhiên `--release` không tự đảm bảo các third-party JAR trên classpath cũng hỗ trợ Java 8. Vẫn cần kiểm tra dependency metadata, bytecode và thử chạy trên JDK 8 thật khi đó là yêu cầu hỗ trợ.

## 12. Không để compiler “nhìn thấy” API chỉ xuất hiện ở nhánh cao

Giả sử root `PublicClient` gọi:

~~~java
return Java17OnlyHelper.fastPath(input);
~~~

nhưng `Java17OnlyHelper` chỉ ở `META-INF/versions/17`. Root compile chỉ thành công nếu build vô tình dùng nhánh 17 trên classpath; trên Java 8, lời gọi sẽ không resolve được.

Do đó:

1. Compile root với release target tối thiểu.
2. Không đưa versioned output của nhánh cao vào root compile classpath.
3. Phân tích static references bằng `jdeps`.
4. Chạy root trên JDK tối thiểu trong clean test environment.
5. Test những đường code có thể bị lazy loading, không chỉ app startup.

MRJAR không phải phép “runtime feature flag” cho phép root tham chiếu tùy ý vào class không tồn tại trên runtime cũ.

## 13. API parity phải kiểm tra trên compiled artifacts

Đối với mỗi public/protected class, cần so sánh output sau compile:

~~~text
Root public API
   ↕
JDK 9 selected public API
   ↕
JDK 17 selected public API
   ↕
JDK 21 selected public API
~~~

Đặt câu hỏi:

- Cùng class name và khả năng truy cập?
- Cùng public/protected constructor signatures?
- Cùng public/protected field names/types/modifiers?
- Cùng method descriptors và static/instance flags?
- Cùng generic signatures quan trọng với source consumers?
- Cùng superclass/interfaces và type relationships?
- Không có public method/class mới ngoài hợp đồng root?
- Annotations/reflection/serialization có còn ý nghĩa đúng?

### 13.1. Kiểm tra bằng `javap --multi-release`

Ví dụ:

~~~bash
javap --multi-release base \
  -classpath build/hex-digest.jar \
  -public -s example.crypto.HexDigest

javap --multi-release 17 \
  -classpath build/hex-digest.jar \
  -public -s example.crypto.HexDigest
~~~

`-s` cho thấy JVM descriptors. `-public` hữu ích để kiểm tra public members; với thư viện mà protected API quan trọng, dùng `-protected` hoặc kết hợp công cụ API diff phù hợp.

Trong môi trường JDK/tool version hỗ trợ, `javap --multi-release VERSION` giúp chọn view tương ứng. Không giả định lệnh `javap -classpath file.jar Foo` luôn nhìn nhánh đang chạy nếu không chỉ định version.

### 13.2. `jar --validate` là lớp kiểm tra đầu

~~~bash
jar --validate --file build/hex-digest.jar
~~~

Theo `jar` tool documentation, validator có thể kiểm tra integrity và tính nhất quán API export qua các versioned entries. Nếu công cụ báo lỗi, xử lý trước khi phát hành.

**Nhưng đây không phải chứng nhận toàn diện:** JAR File Specification lưu ý việc kiểm tra mọi khía cạnh public API rất khó và runtime không bắt buộc xác thực API parity. Kiểm tra binary signatures vẫn cần kết hợp với compile tests, reflection behavior và end-to-end tests trên JDK thực.

### 13.3. So sánh API một cách có chủ đích

Nếu project dùng công cụ API diff như japicmp, Revapi hoặc một framework compatibility riêng, hãy xác nhận công cụ đó có biết MRJAR và chọn đúng variant. Một tool đọc root entry như ZIP rồi báo “không thay đổi” không chứng minh nhánh 21 tương thích.

Kết quả API diff phải gắn với **đúng class view theo release** và chính sách được hỗ trợ, không chỉ version Maven của cả JAR.

## 14. Công khai API qua generics, bridge methods và annotations

Binary compatibility đôi khi phức tạp hơn tên class/method đơn thuần:

~~~java
public interface Repository<T> {
    T find(String id);
}
~~~

Compiler có thể sinh bridge methods khi override generic methods. Một thay đổi class hierarchy hoặc generic signature ở versioned class có thể khiến bridge methods khác và tạo lỗi liên kết khi consumer được compile với một view rồi chạy với view khác.

Các điểm cần xét thêm:

- Generic `Signature` attribute.
- Bridge và synthetic methods có ảnh hưởng runtime.
- Annotations có retention `RUNTIME` được frameworks đọc.
- Parameter names/annotations nếu dependency injection, serialization hoặc reflection dùng.
- Checked exceptions trong method contracts.
- Default interface methods và static/instance access.
- Public nested classes, enum constants, records và sealed types.

Đặc tả MRJAR yêu cầu exported API đồng nhất; trong thực hành, **compatibility policy của thư viện** nên bao phủ cả các metadata mà consumer/tooling coi là hợp đồng.

### 14.1. Giữ cùng signature nhưng đổi annotation có thể phá behavior

Hai nhánh cùng có:

~~~java
public String encode(String value)
~~~

nhưng một nhánh có validation annotation hoặc JSON annotation khác có thể làm framework xử lý khác. Đây là lý do nên kiểm thử reflection, serialization và integration paths trên từng runtime, không chỉ so API text.

## 15. Public constant và giá trị compile-time là trường hợp đặc biệt

Giả sử public class có:

~~~java
public static final int MAX_CHUNK_SIZE = 1024;
~~~

Nếu nhánh 17 thay giá trị thành `2048` mà vẫn cùng field signature, API surface nhìn qua vẫn tương tự, nhưng consumer Java có thể đã **inline** giá trị compile-time constant khi biên dịch. Caller cũ có thể dùng `1024` ngay cả trên runtime chọn nhánh 17.

Do đó, không nên biến các hằng số public compile-time thành cách công bố capability khác theo JDK. Nếu giá trị thực sự phụ thuộc runtime, có thể cung cấp **method public giữ cùng signature** trong mọi nhánh:

~~~java
public static int recommendedChunkSize()
~~~

Nhưng việc kết quả method khác nhau vẫn phải phù hợp hợp đồng nghiệp vụ được tài liệu hóa. Ví dụ một giá trị chỉ là gợi ý hiệu năng có thể chấp nhận thay đổi; một giá trị tham gia protocol handshake hoặc định dạng dữ liệu có thể không được phép khác.

## 16. Mỗi nhánh có quyền dùng Java APIs nào?

Giả sử thư viện có root Java 8, nhánh 17 và 21.

| Code nằm ở | Có thể dùng Java SE APIs từ | Không được phụ thuộc |
| --- | --- | --- |
| Root | Mức Java tối thiểu (ở đây Java 8) | Java 9/17/21-only APIs |
| `versions/17` | APIs tồn tại tới Java 17 | Java 18–21-only APIs |
| `versions/21` | APIs tồn tại tới Java 21 | APIs ra sau Java 21 |

Đây là quy tắc theo **runtime release tương ứng**. Java 21 branch có thể dùng `record` hoặc Java 21 APIs nếu được chuẩn hóa/cho phép ở release đó; root không thể trực tiếp dùng những cú pháp/API mới ấy.

### 16.1. APIs bị bỏ hoặc thay behavior

Không phải “JDK cao hơn” đồng nghĩa mọi API cũ giữ nguyên. Một nhánh 21 có thể cần thay implementation vì API/module từ Java 8 không còn được đóng gói. MRJAR giúp thực hiện thay đổi nội bộ trong khi giữ public API, nhưng phải test behavior như security defaults, locale, timezone, TLS và serialization.

### 16.2. Preview features

Không nên coi preview features là nền tảng ổn định cho API công khai trong MRJAR. Chúng có yêu cầu compiler/runtime flags phụ thuộc release và có thể thay đổi qua JDK. Nếu dùng ở implementation của nhánh cao, cần kiểm soát build flags và runtime policy rất chặt; trong thư viện phát hành rộng, thường nên ưu tiên APIs đã chuẩn hóa.

## 17. Branch fallback không có nghĩa mọi kết hợp class đều an toàn

Một runtime Java 21 có thể chọn một số class từ nhánh 21, một số từ 17 và phần còn lại từ root. Những class đó phải **tương thích với nhau** ở runtime.

Ví dụ:

~~~text
Root:                  PublicCodec + InternalBuffer
META-INF/versions/17:  PublicCodec + FastBuffer
META-INF/versions/21:  PublicCodec
~~~

Ở Java 21, `PublicCodec` được lấy từ nhánh 21. `FastBuffer` không có biến thể 21 nên có thể được lấy từ nhánh 17 nếu được lookup. `InternalBuffer` có thể vẫn từ root.

Điều cần kiểm tra:

- Nhánh 21 có vô tình gọi một method của helper 17 mà chưa từng có không?
- Helper của nhánh cao có tồn tại với class-file target không vượt runtime không?
- Có dùng package-private APIs khác nhau gây `NoSuchMethodError` không?
- Có initialization/serialization state thay đổi giữa những helper được chọn từ nhánh khác nhau không?

Không chỉ test “Java 21 dùng version 21”: nó dùng **một tập entry hiệu lực** sau quy tắc fallback.

## 18. Một ma trận test cần có cho MRJAR

Với các branch root, 9, 17 và 21:

| Runtime JDK | Nhánh hiệu lực đối với class có đủ variants | Bộ test cần chạy |
| --- | --- | --- |
| Java 8 | root | Base API, minimum runtime, behavior, dependencies |
| Java 9 | 9 | Java 9 branch và module behavior nếu dùng |
| Java 11 | 9 | Fallback 9 và JDK 11 environment changes |
| Java 17 | 17 | Branch 17, Java 17 APIs, reflection/serialization |
| Java 19 | 17 | Fallback 17 và Java 19 behavior nếu hỗ trợ |
| Java 21 | 21 | Branch 21, class-file 65, integration |
| Java 23 | 21 | Fallback 21 và newer runtime compatibility |

Nếu thư viện chỉ cam kết Java 8, 17 và 21, đây có thể là bộ runtime tối thiểu. Tuy nhiên nếu sản phẩm tuyên bố hỗ trợ **mọi Java LTS hoặc mọi release giữa các mốc**, hãy chọn test matrix phản ánh lời cam kết đó. Cơ chế branch fallback có thể làm lỗi chỉ xuất hiện ở một khoảng runtime.

### 18.1. Không dùng một JDK để giả lập toàn bộ runtime

`javap --multi-release 8/17/21` và property chọn view có thể giúp phân tích class, nhưng không thay việc khởi chạy JVM phiên bản thật. Java 8 có module, class-loading, TLS và GC behavior khác Java 17/21.

### 18.2. Test từng variant và đường giao nhau

Đừng chỉ kiểm tra `Feature.class` được chọn. Cần test method có liên hệ helper classes, service providers, resources, runtime dependencies và những class khởi tạo muộn.

Một MRJAR nhiều branches có thể xanh ở Java 8 và 21 nhưng fail Java 11 do nhánh 9 dùng một assumption không còn đúng. Vì thế cần test **từng vùng runtime thực tế**.

## 19. Kiểm thử public API bằng consumer đã compile sẵn

Một nguồn lỗi quan trọng là consumer được compile trên runtime cao nhưng triển khai trên runtime thấp còn được thư viện hỗ trợ. Nếu public API khác giữa các nhánh, lỗi chỉ xuất hiện khi JVM resolve method/class.

Test đề xuất:

1. Compile một consumer dùng **root public API** theo mức Java tối thiểu.
2. Giữ nguyên consumer bytecode.
3. Chạy consumer với cùng MRJAR trên các JDK mục tiêu.
4. Đảm bảo không có `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` hoặc behavior drift.
5. Nếu thư viện cho phép consumer compile trên JDK mới và vẫn chạy trên JDK cũ, compile thêm consumer trên release phù hợp rồi test chuyển chiều theo chính sách sản phẩm.

Ví dụ consumer sử dụng:

~~~java
import example.crypto.HexDigest;

final class Consumer {
    static String hash(byte[] input) {
        return HexDigest.sha256Hex(input);
    }
}
~~~

Consumer không cần biết runtime chọn root hay nhánh 17. Đó chính là **API contract ổn định** mà MRJAR hướng tới.

### 19.1. Compile bằng JDK mới chưa chứng minh consumer chạy được trên JDK cũ

Ngay cả nếu public API giống, compiler có thể tạo class-file version mới hoặc consumer vô tình gọi Java API mới. Khi xác nhận compatibility, phải ghi `--release`, dependencies và JVM test tương ứng.

## 20. `jdeps --multi-release`: phân tích dependency của từng nhánh

`jdeps` có khả năng phân tích multi-release JAR theo release view:

~~~bash
jdeps --multi-release base \
  --summary build/hex-digest.jar

jdeps --multi-release 17 \
  --summary build/hex-digest.jar

jdeps --multi-release 21 \
  --summary build/hex-digest.jar
~~~

`base` có nghĩa xem entries ở root; version `17` hoặc `21` là mức dùng để chọn class variants. Đừng nhầm `jdeps --multi-release 21` với việc khởi chạy test trên Java 21.

### 20.1. Phát hiện JDK internal APIs

~~~bash
jdeps --multi-release 17 \
  --jdk-internals build/hex-digest.jar
~~~

Nếu một branch phụ thuộc internal JDK APIs, hãy đánh giá khả năng bị strong encapsulation hoặc API removal ảnh hưởng. `jdeps` không luôn thấy reflection động bằng tên class trong string, native code hoặc runtime-generated bytecode; cần kết hợp smoke/integration tests.

### 20.2. Phát hiện missing dependencies

~~~bash
jdeps --multi-release 21 \
  --missing-deps build/hex-digest.jar
~~~

Đọc kết quả trong ngữ cảnh classpath/module path đầy đủ, vì một missing reference ở phân tích tĩnh có thể đến từ optional dependency hoặc dependency chưa được đưa vào môi trường phân tích. Không coi mọi warning là lỗi production nhưng cũng không tự bỏ qua.

## 21. Kiểm tra trực tiếp bytecode từng nhánh

`javap` không chỉ in signature mà còn disassemble:

~~~bash
javap --multi-release base \
  -classpath build/hex-digest.jar \
  -c -private example.crypto.HexDigest

javap --multi-release 17 \
  -classpath build/hex-digest.jar \
  -c -private example.crypto.HexDigest
~~~

Ở ví dụ SHA-256, base có vòng lặp chuyển hex, còn Java 17 branch có thể có lời gọi tới `java/util/HexFormat`.

Ngoài ra:

~~~bash
javap --multi-release 17 \
  -classpath build/hex-digest.jar \
  -verbose example.crypto.HexDigest
~~~

Xác nhận `major version` của class và những method references trong constant pool. Đừng lấy output của một class trong root rồi kết luận mọi class under `META-INF/versions/17` cũng dùng cùng bytecode/API.

### 21.1. Không phát hành chỉ dựa trên signature diff

Disassembly giúp xác minh sự tồn tại của branch-specific implementation, nhưng không kiểm tra nghiệp vụ. Một nhánh có thể sử dụng đúng Java 17 API nhưng xử lý byte rỗng hoặc Unicode khác base. Test cần bao phủ dữ liệu/behavior.

## 22. Kiểm thử behavior theo từng nhóm input

Với `HexDigest.sha256Hex`, các case nên bao gồm:

- Input `byte[0]`.
- Một byte dương/âm khi biểu diễn dưới dạng signed Java `byte`.
- Chuỗi ASCII chuẩn.
- Dữ liệu UTF-8 nhiều byte, nếu consumer chuyển text thành bytes.
- Payload lớn để kiểm tra hiệu năng/bộ nhớ.
- `null` và exception contract (cần chốt behavior mong đợi).
- Đồng thời từ nhiều threads.

Ví dụ JUnit 5 (chỉ mô tả testcase):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import example.crypto.HexDigest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class HexDigestContractTest {
    @Test
    void sameHashOnEverySupportedJdk() {
        byte[] input = "hello".getBytes(StandardCharsets.UTF_8);

        assertEquals(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            HexDigest.sha256Hex(input)
        );
    }
}
~~~

Test này có giá trị khi chạy **cùng test contract** trên các JVM thật, với JAR đã đóng gói. Không chỉ chạy test trực tiếp trên thư mục output của nhánh 17; cách đó có thể bỏ qua logic MRJAR selection/fallback.

### 22.1. Có cần so sánh performance không?

MRJAR thường tồn tại để tối ưu theo JDK. Vì vậy nên benchmark trong điều kiện công bằng: warmup, input distribution, JIT/GC, cùng hardware và JVM configuration nếu có thể.

Nhưng không ưu tiên performance đến mức làm mất correctness: branch Java 21 trả kết quả khác base không phải “tối ưu hợp lệ” chỉ vì nhanh hơn.

## 23. Kiểm thử serialization và persistent data

Một public class có cùng methods nhưng khác fields nội bộ giữa root và nhánh 17 có thể tác động Java serialization, JSON/XML mapping, persistence hoặc reflection.

Ví dụ:

~~~java
public final class SessionState implements Serializable {
    private static final long serialVersionUID = 1L;
    private final String sessionId;
    // Các field implementation còn lại có thể khác theo nhánh.
}
~~~

Nếu root và nhánh 17 cùng `serialVersionUID` nhưng serialized fields khác, dữ liệu do Java 8 ghi chưa chắc khôi phục được đúng trên Java 17. `serialVersionUID` không tự làm schema conversion.

Do đó, nếu exposed classes hoặc DTO tham gia persistence:

1. Tạo fixture dữ liệu bằng writer trên Java 8.
2. Đọc fixture trên Java 17/21.
3. Tạo fixture bằng writer trên Java 17/21.
4. Đọc bằng Java 8 nếu rollback/interoperability yêu cầu.
5. Kiểm tra invariant và business meaning, không chỉ exception.

MRJAR không thay data schema versioning. Với dữ liệu lâu dài, thường nên giữ serialized DTO format ổn định hoặc chọn schema-based format thích hợp.

## 24. Resources: mọi file được chọn theo version giống class?

JAR File Specification cho phép những resource entries phù hợp ở versioned directory, ngoài class files. Tuy nhiên, một số vùng trong `META-INF` có quy tắc riêng và không được version hóa như resource thường.

### 24.1. Ví dụ resource theo runtime

~~~text
Root:
  example/config/defaults.properties

META-INF/versions/17:
  example/config/defaults.properties
~~~

Khi resource lookup được thực hiện qua API/class loader nhận biết MRJAR, resource được chọn có thể theo runtime release. Nhưng nếu code tự đọc ZIP/JAR entries hoặc dùng loader tùy chỉnh, kết quả có thể khác.

### 24.2. Không version hóa `META-INF/services` theo cách trên

Không tạo:

~~~text
META-INF/versions/17/META-INF/services/example.spi.Service
~~~

và kỳ vọng nó được xử lý như service configuration versioned tiêu chuẩn. `META-INF` là vùng có quy tắc riêng; provider configuration nằm dưới `META-INF/services` không phải resource có thể áp dụng cách versioning thông thường.

Nếu service implementation cần khác theo runtime, thiết kế provider classes và registration phù hợp module/classpath, đồng thời kiểm tra ServiceLoader trên các JDK đã hỗ trợ.

## 25. Java 8 nhìn thấy gì trong multi-release JAR?

Java 8 không hỗ trợ MRJAR selection. Nó xử lý JAR theo mô hình truyền thống, dùng root classes. Các entries `META-INF/versions/N` chỉ nằm trong ZIP/JAR như dữ liệu mà class loader truyền thống không dùng để override root classes.

Hệ quả:

- Root classes **phải** chạy được trên Java 8 nếu đó là Java minimum.
- Một class public chỉ tồn tại ở nhánh 17 không biến thành public class dùng được trên Java 8.
- Root không thể phụ thuộc vào Java 17-only types.
- Manifest không tự cung cấp compatibility shim.
- Một plugin/agent cũ tự quét mọi `.class` trong archive có thể cố đọc bytes Java 17 và lỗi, dù Java 8 runtime không chọn class ấy.

Điểm cuối quan trọng khi dùng bytecode scanners, code quality tools hoặc shading plugin: **tool quét ZIP thô có thể xem cả những classes mà runtime sẽ không bao giờ tải trên Java 8**.

## 26. Multi-release JAR và Java Platform Module System

MRJAR có thể là:

- Một JAR không modular đặt trên **classpath**.
- Một JAR không có module descriptor đặt trên **module path** như automatic module.
- Một **explicit modular MRJAR** có `module-info.class` ở root hoặc một versioned directory phù hợp.

Những dạng đó có cách kiểm soát exports, opens, requires và service provider khác nhau.

### 26.1. `module-info.class` ở nhánh 9

Thư viện giữ root hỗ trợ Java 8 có thể đặt module descriptor ở:

~~~text
META-INF/versions/9/module-info.class
~~~

để trở thành explicit module khi dùng module path trên JDK phù hợp. Điều này cho phép cùng artifact tương thích Java 8 theo classpath truyền thống nhưng khai báo module ở JDK mới.

Ví dụ descriptor minh họa:

~~~java
module example.crypto {
    exports example.crypto;
}
~~~

Việc có descriptor hợp lệ không đồng nghĩa mọi framework reflection tự hoạt động; có thể cần xem `opens`, dependencies và runtime module graph.

### 26.2. Versioned module descriptors có giới hạn chặt

Theo JAR File Specification, một versioned `module-info.class` ghi đè descriptor cũ phải giữ cùng module descriptor, ngoại trừ những khác biệt được cho phép cụ thể, bao gồm một số **non-transitive requires** với `java.*`/`jdk.*` modules và `uses` clauses.

Không dùng `module-info.class` của nhánh 21 để âm thầm đổi tên module, thay exported packages hoặc public module contract. Đặc tả yêu cầu bảo toàn compatibility; tool có thể kiểm tra nhưng runtime không phải bộ bảo đảm toàn diện.

### 26.3. Classpath và module path đều cần test khi hỗ trợ

Một library có thể hoạt động tốt trên classpath nhưng fail ở module path do exports/opens hoặc service loading. Nếu sản phẩm tuyên bố hỗ trợ cả hai, test matrix nên có hai chiều:

~~~text
JDK 17 + classpath
JDK 17 + module path
JDK 21 + classpath
JDK 21 + module path
~~~

Không dùng kết quả classpath-only test để suy ra module-path behavior.

## 27. `JarFile`, `ZipFile` và cách nhìn một JAR trong tooling

`java.util.jar.JarFile` có hỗ trợ multi-release processing, nhưng **cách khởi tạo JarFile** và runtime version view ảnh hưởng những entries được trả về.

Java API cho phép chỉ định một `Runtime.Version` khi mở JarFile để chọn view theo release. Ngược lại, `ZipFile` đọc entry ZIP thực tế; việc liệt kê như ZIP thuần không tự áp dụng mọi quy tắc logical class selection của MRJAR.

### 27.1. Một bẫy khi tự viết scanner

Ví dụ pseudo-code:

~~~text
for each zip entry whose name ends with .class:
    read bytecode
    analyze as Java 8 class
~~~

Scanner sẽ gặp cả `META-INF/versions/17/...` và có thể báo “Unsupported class file major version 61”, dù root hỗ trợ Java 8. Vấn đề là scanner đang đọc **all physical entries** nhưng hiểu sai rằng chúng đều phải được nạp trên Java 8.

Giải pháp: quyết định tool phân tích **toàn bộ variants** hay **logical view của một runtime**, dùng API/tool MRJAR-aware hoặc xử lý versioned entries theo quy tắc rõ ràng.

### 27.2. Ghi rõ chế độ tool khi kiểm kê

Hai nhu cầu khác nhau:

- **Artifact audit:** xem tất cả entries, bao gồm từng versioned class để phát hiện malicious/stale/unexpected binaries.
- **Runtime-specific API/dependency analysis:** xem đúng effective entries mà runtime Java `N` sẽ chọn.

Không trộn hai kiểu báo cáo rồi kết luận một nhánh đã được kiểm thử.

## 28. Shading, fat JAR, Spring Boot launcher và đóng gói khác

Một MRJAR có thể bị thay đổi bởi quá trình packaging:

- Shading/relocation đổi package/class names.
- Fat JAR plugin gộp nhiều dependency jars.
- Nested JAR launcher hoặc custom class loader.
- Assembly plugin sao chép entries nhưng mất manifest.
- Minifier/obfuscator xử lý class ở root mà bỏ qua versioned classes.
- Repackager làm mất `META-INF/versions` hoặc chọn một branch cố định.

Không có quy tắc “mọi fat JAR đều hỗ trợ hoặc đều không hỗ trợ MRJAR”. Tùy phiên bản launcher/plugin và cách đóng gói. Cần kiểm tra **artifact cuối cùng** chứ không chỉ JAR gốc trong cache Maven.

### 28.1. Các phép kiểm tra hậu đóng gói

~~~bash
jar --list --file build/final-app.jar
jar --validate --file build/final-app.jar
~~~

Nếu `final-app.jar` là một executable JAR có cấu trúc nested và loader riêng, `jar --validate` không thể thay end-to-end test của launcher đó. Cần chạy ứng dụng từ artifact cuối trên từng JDK, xác minh class loading và logs.

### 28.2. Duplicate entries và relocation

Hai dependencies đều chứa `META-INF/versions/17/example/Codec.class` có thể tạo conflict khi gộp. Shading cần quy tắc xử lý duplicate entries, package relocation và manifest nhất quán; “first wins” thiếu kiểm soát có thể khiến một JAR runtime dùng sai biến thể.

## 29. Signing và integrity của multi-release JAR

MRJAR có thể được ký như JAR thông thường, nhưng cần nhớ mỗi versioned entry là dữ liệu trong archive và có thể có signature metadata riêng theo quy tắc JAR signing.

Những thay đổi sau signing:

- Thêm/xóa class ở một nhánh.
- Shading/relocation.
- Thay manifest.
- Recompress/repackage các entries theo cách thay đổi dữ liệu được ký.

có thể làm signature verification thất bại hoặc làm mất thông tin provenance. Nếu tổ chức có yêu cầu ký artifact, hãy **đóng gói xong rồi ký**, sau đó xác minh chính artifact sẽ phát hành.

Đừng lấy việc một JVM chọn đúng class làm bằng chứng JAR có nguồn gốc đáng tin. Integrity/signature verification và runtime branch selection là những chiều kiểm tra khác nhau.

## 30. Maven: cách tổ chức build nhiều release

Maven có hướng dẫn chính thức **Guide to Multi-Release JARs**. Ý tưởng cơ bản:

1. Compile root sources với Java release tối thiểu.
2. Có một compiler execution riêng cho mỗi branch cao hơn.
3. Đưa output branch vào đúng `META-INF/versions/N`.
4. Dùng JAR plugin để đóng gói MRJAR và bảo đảm manifest.
5. Kiểm tra JAR sau package bằng `jar --validate` và test nhiều JDK.

Trong những phiên bản Maven Compiler Plugin phù hợp, cấu hình `multiReleaseOutput` cho execution của nhánh có thể giúp output nằm dưới directory versioned.

### 30.1. Cần kiểm tra version plugin thay vì copy POM bất kỳ

Maven Compiler Plugin và Maven JAR Plugin có các features/parameters thay đổi theo release. Ví dụ `multiReleaseOutput` hoặc cơ chế tự nhận diện `Multi-Release` cần được đối chiếu với **phiên bản plugin thực tế**. Không lấy một snippet cũ rồi mặc định nó còn hợp lệ ở mọi major version.

Ví dụ mô hình:

~~~text
compile-main:
  source roots = src/main/java
  release      = 8
  output       = target/classes

compile-java17:
  source roots = src/main/java17
  release      = 17
  output       = target/classes/META-INF/versions/17

jar:
  inputs       = target/classes
  manifest     = Multi-Release: true
  validate     = after packaging
~~~

Đây là **mô hình cấu hình**, không phải một file POM có thể copy nguyên. Khi áp dụng, phải quản lý source roots, generated sources, compiler executions, dependencies và lifecycle phases đúng release/plugin.

### 30.2. Test bằng JVM khác Maven runtime

Maven có thể chạy trên JDK 21 nhưng compile root bằng `--release 8`. Các plugin/test forks cũng có thể chạy JVM khác. Nếu CI chỉ chạy `mvn test` trên JVM 21, nhánh base không được chạy end-to-end trên Java 8 chỉ nhờ compiler target 8.

Muốn test Java 8 và 17, cần cấu hình test runner/toolchains hoặc CI matrix thực sự dùng những JVM đó.

## 31. Gradle: source sets và nhiệm vụ đóng gói

Với Gradle, có thể tạo compilation task riêng cho branch, dùng toolchain và `options.release` thích hợp. Ví dụ **khung Groovy DSL minh họa**:

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
    options.release = 8
}

def compile17 = tasks.register('compileJava17', JavaCompile) {
    source = fileTree('src/main/java17')
    classpath = files(sourceSets.main.output, configurations.compileClasspath)
    destinationDirectory = layout.buildDirectory.dir('classes/java/java17')
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    options.release = 17
}

tasks.named('jar', Jar) {
    dependsOn compile17
    manifest {
        attributes('Multi-Release': 'true')
    }
    from(compile17.flatMap { it.destinationDirectory }) {
        into 'META-INF/versions/17'
    }
}
~~~

Đây là ví dụ tổ chức tasks cho dự án Java đơn giản, không phải cấu hình production đầy đủ. Nó giả định Gradle version hỗ trợ các APIs đang dùng và có JDK/toolchain phù hợp; thư mục source, dependency classpath, test source sets và reproducibility settings phải điều chỉnh theo dự án.

**Quan trọng:** `options.release = 8` đặt cho JavaCompile tasks nói chung, nên task `compileJava17` phải ghi đè thành 17 như trong ví dụ. Không được để một rule áp dụng sau đó vô tình thay `release` của branch.

### 31.1. Tách compile và test tasks

CI có thể chạy:

~~~text
assemble MRJAR
validate JAR
testOnJava8  -> root selected
testOnJava17 -> Java17 selected
testOnJava21 -> Java17 fallback (nếu không có nhánh 21)
~~~

Sự tồn tại của Gradle Java toolchain không tự chạy tất cả JVM test variants. Cần tạo/khai báo riêng Test tasks hoặc CI jobs theo chính sách hỗ trợ.

## 32. API parity checks không đồng nghĩa kiểm tra runtime behavior

Giả sử `jar --validate` báo thành công. Điều đó vẫn để lại những câu hỏi:

- Nhánh 17 có dùng API không còn hoạt động đúng trên JDK 21?
- Có class loader tùy chỉnh không chọn đúng nhánh?
- Framework reflection/JSON serializer có đọc fields/annotations giống nhau không?
- Service resources và module descriptors có đúng không?
- Có JDK-specific behavior trong security, TLS, locale, timezone hoặc file handling không?
- Native/JNI/agent dependencies có tương thích không?
- Performance regression có vượt budget không?

Do đó, pipeline phải có **hai cửa độc lập**:

**Cửa 1 — Structural/packaging/API:** manifest, entries, class versions, exported signatures và module constraints.

**Cửa 2 — Execution/behavior:** cùng contract tests thực thi trên các JDK và môi trường triển khai dự kiến.

Một MRJAR “có cấu trúc hợp lệ” nhưng chỉ chạy test ở Java 21 chưa thể được công bố là hỗ trợ Java 8.

## 33. Các lỗi thường gặp và nơi điều tra

| Triệu chứng | Khả năng nguyên nhân | Bước điều tra |
| --- | --- | --- |
| Java 17 vẫn chạy implementation root | Manifest thiếu `Multi-Release: true` hoặc loader không hỗ trợ | Kiểm tra manifest, final JAR, launcher |
| Java 8 báo `UnsupportedClassVersionError` | Root chứa bytecode cao hơn Java 8 | `javap -verbose` root, compile release |
| Java 17 báo `UnsupportedClassVersionError` | `versions/17` chứa major >61 | Kiểm tra compile task, artifact entry |
| `NoSuchMethodError` chỉ trên một JDK | API hoặc inter-branch helper mismatch | `javap --multi-release`, class loading |
| `NoSuchFieldError` khi consumer đổi runtime | Field API lệch giữa variants | API diff, consumer binary tests |
| `ClassNotFoundException` từ branch cao | Branch tham chiếu class/dependency không có | `jdeps --multi-release`, module/classpath |
| `jar --validate` báo API khác nhau | Public/protected signatures lệch | So root và branch bằng `javap` |
| Test pass từ build dir nhưng fail trên packaged JAR | Layout hoặc manifest bị mất/sai | Chạy test với final JAR |
| Framework không tìm service provider | Provider config bị version hóa sai | Xem `META-INF/services`, ServiceLoader |
| Module path fail, classpath pass | `module-info.class`, exports/opens/requires | `jar --describe-module`, JPMS tests |
| Shaded JAR mất nhánh 17 | Packaging tool không giữ entries hoặc rewrite manifest | Kiểm tra final artifact tree |
| Coverage tool fail trên root-compatible JAR | Scanner cố parse mọi class trong versions/21 | Nâng bytecode tool hoặc MRJAR-aware filtering |
| Java 21 kết quả khác Java 17 | Behavioral drift, default/locale/serialization | Golden fixtures, integration tests |
| Native agent fail ở Java mới | Agent/ASM/JNI không hỗ trợ runtime | Agent support matrix, class-file version |

Một triệu chứng có thể có nhiều nguyên nhân. Hãy xác định **class file và JAR nào thật sự được nạp**, sau đó mới chỉnh build.

## 34. Diagnostic commands theo đúng mục tiêu

### 34.1. Xem cấu trúc và manifest

~~~bash
jar --list --file build/library.jar
jar --validate --file build/library.jar
~~~

Nếu cần xem manifest, có thể extract để kiểm tra trong một workspace tạm được phép hoặc dùng công cụ ZIP/JAR inspection phù hợp. Đừng sửa trực tiếp JAR đã ký chỉ để xem manifest.

### 34.2. Xem API và bytecode theo branch

~~~bash
javap --multi-release base \
  -classpath build/library.jar -public -s example.api.Feature

javap --multi-release 17 \
  -classpath build/library.jar -public -s example.api.Feature

javap --multi-release 21 \
  -classpath build/library.jar -public -s example.api.Feature
~~~

### 34.3. Xem dependency theo branch

~~~bash
jdeps --multi-release base \
  --summary build/library.jar

jdeps --multi-release 17 \
  --summary build/library.jar
~~~

### 34.4. Xác định runtime/JVM đã dùng

~~~bash
java -version
javac -version
jar --version
~~~

Trong CI, lưu JDK vendor/build/runtime image; `java -version` ở máy developer không chứng minh container production dùng cùng JVM.

### 34.5. Xem class load tại runtime khi cần

Trên JDK hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info \
  -cp build/library.jar:build/consumer-classes \
  example.consumer.Main
~~~

Logs có thể nhiều và thông tin chi tiết khác theo JVM; hãy chọn mức/đích log phù hợp, lưu dữ liệu an toàn và kết hợp với inspection của final JAR.

## 35. Test matrix nên mở rộng ra môi trường đóng gói

Đối với thư viện được dùng cả trên classpath và module path, hoặc phân phối qua fat JAR và application server:

| Chiều test | Giá trị điển hình |
| --- | --- |
| Runtime JDK | Java 8, 11, 17, 21 theo support policy |
| Packaging | Original MRJAR, shaded JAR, nested/executable JAR nếu dùng |
| Loading mode | Classpath, module path, custom loader nếu được hỗ trợ |
| Consumer | Compile với base API, compile với highest supported API |
| Behavior | Unit contract, integration, reflection/serialization |
| Tooling | JAR validator, API diff, jdeps, coverage, scanner |
| Architecture | OS/container/JDK vendor nếu dependency chịu ảnh hưởng |
| Security | Signature, provenance, modules, TLS/crypto nếu liên quan |

Không cần nhân ma trận vô hạn. Hãy chọn **các tổ hợp thật sự được sản phẩm cam kết hỗ trợ** và những ranh giới có rủi ro cao. Ví dụ Java 8 × module path không phải một tổ hợp hợp lệ theo JPMS, nên không đưa nó vào yêu cầu test như thể có module path trên Java 8.

### 35.1. Điểm quan trọng: test artifact sau packaging

Các project thường compile các branch riêng thành công rồi test từng thư mục output; nhưng lỗi xuất hiện khi JAR Plugin/Shade Plugin tạo artifact cuối. Vì thế phải có test dùng **JAR phát hành thực tế** và cấu hình class loader giống production.

## 36. Quy trình release MRJAR có kiểm soát

1. **Chốt mức Java tối thiểu** và các JDK runtime được hỗ trợ.
2. **Thiết kế public API một lần**; ghi public/protected contract trong module root.
3. **Tách source set cho từng branch**, giữ implementation khác biệt ở nội bộ.
4. **Biên dịch mỗi nhánh với `--release N` tương ứng**, root không được dùng APIs mới.
5. **Đóng gói** manifest và versioned directories đúng.
6. **Kiểm tra final JAR** với `jar --list` và `jar --validate`.
7. **So sánh API view** bằng `javap --multi-release` hoặc công cụ diff MRJAR-aware.
8. **Phân tích dependencies** theo branch bằng `jdeps --multi-release`.
9. **Chạy consumer compatibility tests** trên các runtime/JDK hỗ trợ.
10. **Chạy behavioral/integration tests** với final artifact, kèm resource, service, module và agent paths nếu có.
11. **Kiểm tra shading/signing/provenance** và version của build plugins.
12. **Canary hoặc phát hành thử**, quan sát errors, performance và compatibility metrics.

Làm các bước này thành pipeline tái lập, có logs, checksums và artifact lineage; không dựa vào thao tác sao chép các `.class` bằng tay ở máy một developer.

## 37. Checklist dành cho reviewer

- [ ] Có lý do rõ vì sao dùng MRJAR thay vì chỉ nâng Java minimum hoặc tách artifact.
- [ ] Root classes thực sự chạy được trên runtime tối thiểu đã công bố.
- [ ] Mọi branch dùng đúng `META-INF/versions/N` với `N >= 9`.
- [ ] Manifest của final JAR có `Multi-Release: true` ở main section.
- [ ] Class-file major version không vượt Java release của branch.
- [ ] Không có public/protected API bổ sung/xóa/đổi type tùy nhánh.
- [ ] Public/protected classes và exported packages tuân thủ quy tắc counterpart của JAR spec.
- [ ] Các ngoại lệ modular/non-exported packages (nếu có) được dùng có chủ đích.
- [ ] API generics, bridge, inheritance, annotations/reflection được đánh giá khi có consumer dựa vào.
- [ ] Public constants không đổi giá trị tùy runtime theo cách phá binary/semantic contract.
- [ ] Root không phụ thuộc Java 9+/17+/21+ APIs hoặc helper class chỉ ở branch cao.
- [ ] Branch cao không dùng API Java release cao hơn level của chính branch.
- [ ] Inter-branch fallback và helpers được test.
- [ ] `jar --validate` chạy thành công trên final artifact.
- [ ] `javap --multi-release`/API diff đã so public API theo mỗi view cần hỗ trợ.
- [ ] `jdeps --multi-release` đã kiểm tra dependencies quan trọng của từng view.
- [ ] Test consumer đã compile với base API chạy qua JVM matrix được công bố.
- [ ] Chạy tests trên JDK thực, không chỉ đổi property mô phỏng selection.
- [ ] Contract tests có cases về null/empty/boundaries/concurrency và behavior khác theo runtime.
- [ ] Dữ liệu serialize/persist được test đọc chéo nếu application cần rollback/interoperability.
- [ ] Resource và ServiceLoader behavior không dựa vào version hóa sai `META-INF/services`.
- [ ] Module descriptor/exports/opens được kiểm tra khi JAR được dùng trên module path.
- [ ] Custom class loaders, nested JAR/fat JAR có bằng chứng thực sự hỗ trợ MRJAR.
- [ ] Shading, obfuscation và signing không làm mất/thay entries ngoài ý muốn.
- [ ] Build tool/compiler/test/coverage plugins được pin phiên bản tương thích.
- [ ] Có CI test artifact cuối sau packaging, không chỉ classes folder.
- [ ] Release notes mô tả mức Java hỗ trợ và branch-specific behavior đáng chú ý.

## 38. Những hiểu lầm phổ biến

**“MRJAR cho phép API mới trên Java mới trong cùng JAR.”** Không phải mục đích hợp lệ của MRJAR: exported public API phải đồng nhất qua releases.

**“Cứ đặt `versions/8` là tạo nhánh Java 8.”** Sai. Root là base, versioned directories hợp lệ bắt đầu từ 9.

**“Java 21 luôn chọn directory `versions/21`.”** Chỉ khi entry tương ứng tồn tại; nếu không JVM fallback xuống nhánh thấp hơn/root.

**“Manifest không quan trọng nếu đã có versioned classes.”** Sai. `Multi-Release: true` là dấu hiệu để runtime/tooling nhận MRJAR.

**“Đặt class major 65 dưới `versions/17` sẽ chạy trên Java 17.”** Sai. Tên directory không làm classfile tương thích.

**“Một method public mới chỉ dành cho Java 21 là tối ưu nội bộ.”** Sai nếu exported API khác giữa versions; phải giải quyết bằng versioning API khác.

**“API signature giữ nguyên thì behavior luôn tương thích.”** Sai. Constants, serialization, annotations, locale, security và concurrency có thể khác.

**“`jar --validate` pass nghĩa là mọi thứ đều ổn.”** Không đủ. Đặc tả không yêu cầu validator hoặc JVM kiểm tra toàn bộ API semantics; còn cần runtime/contract tests.

**“Một unit test trên JDK 21 bao phủ tất cả nhánh.”** Sai. Root và nhánh 9/17 chưa chắc đã được chạy.

**“Cùng version JAR nghĩa là class loader chắc chắn lấy cùng bytecode.”** Sai. MRJAR chủ đích thay bytecode theo runtime.

**“`ZipFile` hoặc scanner tùy chỉnh chắc chắn hiểu runtime branch selection.”** Sai. Tool có thể chỉ nhìn physical entries hoặc base.

**“Có thể version hóa `META-INF/services` như các resource thường.”** Sai theo quy tắc MRJAR của `META-INF`.

**“Module descriptor của nhánh 21 có thể export mọi package mới.”** Không phải thay đổi tùy ý: versioned module descriptors có ràng buộc nghiêm ngặt.

**“Shading giữ nguyên MRJAR khi file `.class` vẫn tồn tại.”** Chưa đủ; manifest, directory layout, relocation và loader behavior đều phải được kiểm tra.

**“`--release` của root bảo đảm mọi dependency hỗ trợ Java minimum.”** Sai. Third-party JAR có thể cần runtime mới hơn.

## 39. Tài liệu kỹ thuật và giới hạn của công cụ

Nên đối chiếu tài liệu theo release khi xây dựng hoặc rà soát MRJAR:

- **OpenJDK JEP 238 — Multi-Release JAR Files:** cơ chế thiết kế và mục tiêu.
  https://openjdk.org/jeps/238
- **Java JAR File Specification — Multi-release JAR files:** manifest, layout, selection, class-file constraints, exported API và modular exceptions.
  https://docs.oracle.com/en/java/javase/25/docs/specs/jar/jar.html
- **`jar` Tool Guide:** `--release`, `--validate`, packaging và integrity.
  https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html
- **`javap` Tool Guide:** `--multi-release`, descriptors và disassembly.
  https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- **`jdeps` Tool Guide:** `--multi-release`, dependency analysis và JDK internals.
  https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html
- **Apache Maven — Guide to Multi-Release JARs:** compiler executions và JAR packaging.
  https://maven.apache.org/guides/mini/guide-multi-release-jars.html
- **`java.util.jar.JarFile` API:** runtime version views và cách tooling mở MRJAR.
  https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- **Gradle Java Toolchains và JavaCompile documentation:** compile tasks theo release và packaging task graph.

Các đường dẫn chỉ dẫn tới tài liệu kỹ thuật, không phải bảng chốt phiên bản plugin cho mọi dự án. Khi migration, cần xác nhận plugin/JDK vendor/tool versions thực tế.

## 40. Kết luận

Multi-release JAR cho phép một thư viện giữ **mức Java tối thiểu thấp** trong khi dùng **implementation chuyên biệt** trên runtime mới. Nhưng sự linh hoạt này đi kèm quy tắc quan trọng: **public API được export phải nhất quán giữa các nhánh**; thư viện không được tự biến thành nhiều phiên bản API khác nhau chỉ vì JVM chọn entry ở `META-INF/versions/N`.

Một quy trình an toàn cần giữ root và từng branch ở compile release phù hợp, đóng gói manifest đúng, so sánh API view ở bytecode level, phân tích dependencies và **chạy cùng contract tests trên từng JDK thật**. Đồng thời phải kiểm tra fallback giữa các branches, resource/module loading, shading, signing và artifact thực tế sau packaging.

Hãy coi MRJAR là **một thư viện với nhiều đường thực thi**, không phải một JAR đơn giản có thêm vài class files. Chỉ khi mọi đường thực thi giữ đúng public contract và được kiểm chứng trên những runtime đã cam kết, việc nâng JDK và phân phối thư viện qua nhiều môi trường mới có cơ sở tương thích và vận hành tin cậy.
