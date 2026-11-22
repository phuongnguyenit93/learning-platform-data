# Manifest Multi-Release và `META-INF/versions`

## Mục tiêu

Multi-Release JAR (MR-JAR) cho phép một thư viện phát hành **một file JAR duy nhất** nhưng chứa các phiên bản class hoặc resource khác nhau cho các phiên bản Java khác nhau. JVM chọn nội dung phù hợp với phiên bản runtime đang chạy; các runtime cũ vẫn dùng nội dung nền ở gốc JAR.

Cơ chế này hữu ích khi thư viện cần tận dụng API mới ở JDK mới, tối ưu một phần triển khai hoặc cung cấp resource phù hợp theo phiên bản, đồng thời vẫn duy trì một artifact dùng được trên nhiều thế hệ Java.

Để JVM coi JAR là multi-release, manifest phải có thuộc tính ở main section:

```text
Multi-Release: true
```

Các nội dung thay thế được đặt dưới `META-INF/versions/<N>/`, trong đó `N` là số phiên bản Java dạng số nguyên từ 9 trở lên. Ví dụ `META-INF/versions/17/` chứa nội dung dành cho Java 17 trở lên.

## 1. Cấu trúc của một Multi-Release JAR

Giả sử thư viện có lớp `com.example.mr.FeatureMessage` và resource `com/example/mr/build-info.txt`. JAR có thể được tổ chức như sau:

```text
feature-mr.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/mr/
│       │       ├── FeatureMessage.class
│       │       └── build-info.txt
│       ├── 17/
│       │   └── com/example/mr/
│       │       ├── FeatureMessage.class
│       │       └── build-info.txt
│       └── 21/
│           └── com/example/mr/
│               ├── FeatureMessage.class
│               └── build-info.txt
└── com/example/mr/
    ├── FeatureMessage.class
    └── build-info.txt
```

Thư mục gốc chứa **bản nền**. Các thư mục con của `META-INF/versions` chứa những mục thay thế có cùng đường dẫn logic với mục nền. Ví dụ:

| Nội dung logic | Bản nền | Bản thay thế Java 17 |
|---|---|---|
| Class | `com/example/mr/FeatureMessage.class` | `META-INF/versions/17/com/example/mr/FeatureMessage.class` |
| Resource | `com/example/mr/build-info.txt` | `META-INF/versions/17/com/example/mr/build-info.txt` |

Phần sau `<N>/` là đường dẫn tương đối bên trong JAR. Không lặp lại `META-INF/versions` trong đường dẫn logic.

## 2. Vai trò của thuộc tính Multi-Release

JVM chỉ áp dụng quy tắc chọn phiên bản cho JAR có thuộc tính `Multi-Release: true` trong main section của manifest. Nếu thuộc tính không có hoặc không được đặt thành `true`, các thư mục `META-INF/versions` không được dùng làm nội dung thay thế; ứng dụng nhận bản nền ở gốc JAR.

Manifest tối thiểu:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Đây là thuộc tính của manifest, không phải một file cấu hình riêng. Nó phải nằm trong main section, trước dòng trống phân cách các named section. Khi dùng `jar --release N`, JDK jar tool cũng có thể thiết lập thuộc tính multi-release cho artifact; vẫn nên kiểm tra manifest cuối cùng.

## 3. JVM chọn phiên bản nào?

Khi tìm class hoặc resource trong MR-JAR, runtime chọn mục có phiên bản cao nhất **không vượt quá phiên bản Java đang chạy**. Nếu không có mục thay thế phù hợp, runtime dùng bản nền.

Ví dụ JAR có các bản nền, 9, 17 và 21:

| Runtime | Nội dung được chọn | Lý do |
|---|---|---|
| Java 8 | Bản nền ở gốc JAR | Java 8 không áp dụng cơ chế multi-release |
| Java 11 | `META-INF/versions/9/` | 9 là phiên bản cao nhất không vượt quá 11 |
| Java 17 | `META-INF/versions/17/` | Có bản khớp runtime |
| Java 20 | `META-INF/versions/17/` | 21 lớn hơn runtime nên không được chọn |
| Java 21 hoặc 24 | `META-INF/versions/21/` | 21 là bản cao nhất không vượt runtime |

Nếu một resource không có trong thư mục phiên bản được chọn, việc tìm kiếm tiếp tục theo các phiên bản thấp hơn phù hợp rồi đến bản nền. Vì vậy không cần lặp lại mọi resource trong tất cả thư mục version; chỉ thêm mục thực sự cần thay đổi.

Quy tắc này áp dụng cho cả class và resource. Khi mã gọi `FeatureMessage.class.getResourceAsStream("build-info.txt")`, resource tương ứng trong MR-JAR cũng được chọn theo runtime version.

## 4. Giữ bản nền tương thích và thay thế có kiểm soát

Thiết kế thường gặp là:

- Bản nền được biên dịch với mức Java thấp nhất mà thư viện cần hỗ trợ.
- Bản thay thế trong `META-INF/versions/9`, `/17`, `/21` được biên dịch bằng `javac --release` tương ứng.
- Các lớp thay thế giữ cùng tên nhị phân và tương thích với mã gọi đã biên dịch dựa trên bản nền.

`--release N` kiểm soát cả mức bytecode và tập API nền tảng được phép dùng khi biên dịch. Chỉ dùng `-source` hoặc `-target` không đủ để ngăn mã vô tình tham chiếu API chỉ có ở JDK mới.

Ví dụ bản nền dùng Java 8:

```java
package com.example.mr;

public final class FeatureMessage {
    private FeatureMessage() {}

    public static String message() {
        return "base implementation";
    }
}
```

Bản thay thế Java 17 có cùng package, tên class và chữ ký public:

```java
package com.example.mr;

public final class FeatureMessage {
    private FeatureMessage() {}

    public static String message() {
        return "version 17 implementation";
    }
}
```

Mã gọi được biên dịch dựa trên bản nền. Khi chạy trên Java 17+, JVM chọn class thay thế. Giữ API tương thích là quan trọng: nếu bản thay thế xóa method hoặc đổi chữ ký mà mã gọi cần, có thể phát sinh lỗi liên kết như `NoSuchMethodError` hoặc `NoSuchFieldError`.

## 5. Tạo MR-JAR bằng JDK jar tool

Ví dụ đầy đủ dưới đây tạo một JAR có bản nền Java 8 và các bản thay thế Java 9, 17, 21. Mỗi bản cung cấp cùng API nhưng trả về thông báo khác nhau; resource `build-info.txt` cũng được thay thế theo phiên bản.

Cấu trúc source:

```text
project/
├── src/
│   ├── base/com/example/mr/FeatureMessage.java
│   ├── base/com/example/mr/build-info.txt
│   ├── v9/com/example/mr/FeatureMessage.java
│   ├── v9/com/example/mr/build-info.txt
│   ├── v17/com/example/mr/FeatureMessage.java
│   ├── v17/com/example/mr/build-info.txt
│   ├── v21/com/example/mr/FeatureMessage.java
│   ├── v21/com/example/mr/build-info.txt
│   └── app/com/example/mr/Main.java
├── build/
└── manifest.mf
```

**Bản nền — `src/base/com/example/mr/FeatureMessage.java`**

```java
package com.example.mr;

public final class FeatureMessage {
    private FeatureMessage() {}

    public static String message() {
        return "base implementation";
    }
}
```

**Bản thay thế — ví dụ `src/v17/com/example/mr/FeatureMessage.java`**

```java
package com.example.mr;

public final class FeatureMessage {
    private FeatureMessage() {}

    public static String message() {
        return "version 17 implementation";
    }
}
```

Ở các source root `v9` và `v21`, giữ nguyên tên package, class và chữ ký method, thay nội dung trả về lần lượt thành `version 9 implementation` và `version 21 implementation`.

Resource ở mỗi source root cũng có nội dung tương ứng:

```text
base:  base resource
v9:    version 9 resource
v17:   version 17 resource
v21:   version 21 resource
```

**Ứng dụng kiểm tra — `src/app/com/example/mr/Main.java`**

```java
package com.example.mr;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.JarFile;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(FeatureMessage.message());

        try (InputStream input =
                     FeatureMessage.class.getResourceAsStream("build-info.txt")) {
            if (input == null) {
                throw new IllegalStateException("build-info.txt not found");
            }
            String resource = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println("resource=" + resource);
        }

        if (args.length > 0) {
            try (JarFile jar = new JarFile(args[0])) {
                String multiRelease = jar.getManifest()
                        .getMainAttributes().getValue("Multi-Release");
                System.out.println("multiRelease=" + multiRelease);
            }
        }
    }
}
```

### Biên dịch trên Windows PowerShell

Chạy từ thư mục `project`. Tạo các thư mục output:

```powershell
New-Item -ItemType Directory -Force build/base, build/v9, build/v17, build/v21, build/app
```

Biên dịch bản nền và từng bản thay thế:

```powershell
javac --release 8 -Xlint:-options -d build/base src/base/com/example/mr/FeatureMessage.java
javac --release 9 -d build/v9 src/v9/com/example/mr/FeatureMessage.java
javac --release 17 -d build/v17 src/v17/com/example/mr/FeatureMessage.java
javac --release 21 -d build/v21 src/v21/com/example/mr/FeatureMessage.java
```

`-Xlint:-options` chỉ tắt cảnh báo tùy chọn `--release 8` đã cũ trên compiler mới; nó không thay đổi mức tương thích Java 8 của bytecode nền.

Sao chép resource vào đúng package path trong từng output:

```powershell
Copy-Item src/base/com/example/mr/build-info.txt build/base/com/example/mr/
Copy-Item src/v9/com/example/mr/build-info.txt build/v9/com/example/mr/
Copy-Item src/v17/com/example/mr/build-info.txt build/v17/com/example/mr/
Copy-Item src/v21/com/example/mr/build-info.txt build/v21/com/example/mr/
```

Biên dịch ứng dụng kiểm tra dựa trên bản nền:

```powershell
javac --release 17 -cp build/base -d build/app src/app/com/example/mr/Main.java
```

Tạo file `manifest.mf` với nội dung:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Đóng gói các bản vào một JAR:

```powershell
jar --create --file build/feature-mr.jar --manifest manifest.mf -C build/base . --release 9 -C build/v9 . --release 17 -C build/v17 . --release 21 -C build/v21 .
```

`-C build/base .` đưa bản nền vào gốc JAR. Mỗi cặp `--release N -C build/vN .` đưa nội dung tương ứng vào `META-INF/versions/N/`. Không tự tạo thư mục `META-INF/versions` rồi đặt thêm một tầng `META-INF/versions` bên trong; `jar --release` đã tạo đúng cấu trúc.

### Lệnh tương đương trên Linux hoặc macOS

Dùng `mkdir -p build/base build/v9 build/v17 build/v21 build/app` để tạo thư mục. Các lệnh `javac` và `jar` giống PowerShell. Lệnh sao chép resource:

```bash
cp src/base/com/example/mr/build-info.txt build/base/com/example/mr/
cp src/v9/com/example/mr/build-info.txt build/v9/com/example/mr/
cp src/v17/com/example/mr/build-info.txt build/v17/com/example/mr/
cp src/v21/com/example/mr/build-info.txt build/v21/com/example/mr/
```

## 6. Kiểm tra cấu trúc và manifest

Liệt kê nội dung JAR:

```powershell
jar --list --file build/feature-mr.jar
```

Kiểm tra các mục quan trọng:

```text
META-INF/MANIFEST.MF
com/example/mr/FeatureMessage.class
com/example/mr/build-info.txt
META-INF/versions/9/com/example/mr/FeatureMessage.class
META-INF/versions/17/com/example/mr/FeatureMessage.class
META-INF/versions/21/com/example/mr/FeatureMessage.class
META-INF/versions/21/com/example/mr/build-info.txt
```

Xem lại manifest bằng `jar` hoặc `JarFile` và xác nhận `Multi-Release: true`. Có thể yêu cầu jar tool kiểm tra tính nhất quán của MR-JAR:

```powershell
jar --validate --file build/feature-mr.jar
```

Trên JDK 24.0.2, lệnh validation của JAR ví dụ kết thúc với exit code `0` và không in lỗi.

Với JAR có module descriptor, kiểm tra thêm thông tin module bằng `jar --describe-module --file <jar-file>`. Multi-release chỉ điều khiển việc chọn nội dung theo phiên bản; nó không thay thế việc thiết kế module descriptor, `requires`, `exports` hoặc `opens` đúng.

## 7. Chạy và quan sát lựa chọn phiên bản

Chạy ứng dụng trên JDK 24.0.2. Windows dùng dấu `;` để phân tách class path:

```powershell
java -cp "build/app;build/feature-mr.jar" com.example.mr.Main build/feature-mr.jar
```

Stdout:

```text
version 21 implementation
resource=version 21 resource
multiRelease=true
```

JDK 24 chọn bản 21 vì đây là thư mục version cao nhất không vượt quá runtime.

Trên Linux hoặc macOS, class path dùng dấu `:`:

```bash
java -cp "build/app:build/feature-mr.jar" com.example.mr.Main build/feature-mr.jar
```

### Kiểm tra các mức phiên bản khác nhau

Để kiểm tra lựa chọn mà không cần cài nhiều JDK, có thể dùng thuộc tính hệ thống `jdk.util.jar.version` làm override trong môi trường thử nghiệm:

```powershell
java '-Djdk.util.jar.version=17' -cp "build/app;build/feature-mr.jar" com.example.mr.Main
java '-Djdk.util.jar.version=8' -cp "build/app;build/feature-mr.jar" com.example.mr.Main
```

Kết quả quan sát trên JDK 24.0.2:

```text
jdk.util.jar.version=17:
version 17 implementation
resource=version 17 resource

jdk.util.jar.version=8:
base implementation
resource=base resource
```

Override này hữu ích cho kiểm thử chọn nội dung của JAR. Khi triển khai thông thường, để runtime tự dùng phiên bản Java thực tế; không đặt thuộc tính này như một cách thay thế việc kiểm thử trên JDK mục tiêu.

## 8. Vì sao manifest bắt buộc?

Một JAR có thể chứa các đường dẫn `META-INF/versions/17/...` nhưng nếu manifest không có `Multi-Release: true`, JVM không coi chúng là bản thay thế. Runtime tiếp tục dùng class/resource ở gốc JAR.

Đã kiểm tra trường hợp này bằng cách tạo một JAR có đủ thư mục `META-INF/versions/9`, `/17`, `/21` nhưng không có thuộc tính manifest. Kết quả trên JDK 24.0.2:

```text
base implementation
resource=base resource
multiRelease=null
```

Vì vậy, khi ứng dụng chỉ chạy bản nền dù JAR có các thư mục version, hãy kiểm tra manifest trước khi kiểm tra code.

## 9. Resource cũng được version hóa

Multi-release không chỉ dành cho `.class`. Các resource có thể được thay thế theo cùng quy tắc:

```text
com/example/mr/build-info.txt
META-INF/versions/17/com/example/mr/build-info.txt
```

Khi truy cập resource qua API chuẩn như `Class.getResourceAsStream()` hoặc `ClassLoader.getResourceAsStream()`, runtime áp dụng quy tắc multi-release cho JAR. Ví dụ trong bài dùng `FeatureMessage.class.getResourceAsStream("build-info.txt")` nên resource được chọn cùng phiên bản với lớp.

Nếu dùng API ZIP/JAR mức thấp để đọc entry vật lý, cần chú ý chế độ phiên bản của `JarFile`. Đừng giả định mọi API đọc ZIP đều tự áp dụng cùng quy tắc như class loader.

## 10. Quy tắc tương thích khi thiết kế

- **Giữ bản nền đầy đủ:** mọi class/resource cần cho runtime cũ phải có ở gốc JAR.
- **Giữ tên và chữ ký API ổn định:** class thay thế phải tương thích với mã đã biên dịch dựa trên bản nền.
- **Biên dịch đúng release:** dùng `javac --release N` cho từng source root để không tham chiếu nhầm API của JDK mới hơn.
- **Chỉ thêm bản thay thế khi có lợi:** không cần lặp lại mọi class/resource ở mọi version directory.
- **Dùng số version hợp lệ:** thư mục version phải dùng số nguyên từ 9 trở lên, như `9`, `17`, `21`; không dùng `1.9`, `17-ea` hoặc `8`.
- **Kiểm tra manifest cuối cùng:** thuộc tính `Multi-Release: true` phải có trong main section.
- **Kiểm tra nội dung đóng gói:** dùng `jar --list` để chắc rằng đường dẫn trong `META-INF/versions/N` đúng và không bị lồng thêm thư mục.
- **Kiểm thử cả fallback và override:** chạy bản nền, ít nhất một runtime versioned và runtime mới nhất dự kiến hỗ trợ.
- **Ký sau khi đóng gói:** nếu phát hành JAR có chữ ký, hoàn tất mọi thay đổi rồi mới ký; sửa JAR sau khi ký sẽ làm chữ ký không còn hợp lệ.

## 11. Lỗi thường gặp

- **Runtime luôn dùng bản nền:** kiểm tra `Multi-Release: true`, vị trí `META-INF/versions/N` và tên đường dẫn sau `<N>/`.
- **Runtime chọn sai version:** nhớ rằng JVM chọn version cao nhất không vượt runtime; thư mục version cao hơn runtime sẽ bị bỏ qua.
- **Class mới gây lỗi trên runtime cũ:** kiểm tra bản nền có bytecode/API tương thích và không vô tình đặt class chỉ hỗ trợ JDK mới ở gốc.
- **`NoSuchMethodError` hoặc `NoSuchFieldError`:** bản thay thế đã thay đổi chữ ký mà mã gọi phụ thuộc; giữ binary API tương thích.
- **Resource không thay đổi:** đặt resource vào cùng đường dẫn logic trong `META-INF/versions/N` và đọc qua API resource chuẩn.
- **`jar --validate` báo lỗi:** kiểm tra tên version directory, cấu trúc entry, các bản class trùng hoặc không hợp lệ và manifest.
- **JAR có version directory nhưng không có MR flag:** các entry đó không được xem là nội dung thay thế; kiểm tra main section của manifest.
- **Dùng `--release` nhầm mức:** mỗi source root phải được biên dịch theo đúng feature release mà thư mục version đại diện.
- **Sửa artifact sau khi ký:** tạo lại chữ ký trên JAR cuối cùng sau khi mọi entry đã được đóng gói.

## 12. Checklist phát hành Multi-Release JAR

- [ ] Có bản nền ở gốc JAR cho mọi class/resource cần hỗ trợ runtime cũ.
- [ ] Manifest main section có `Multi-Release: true`.
- [ ] Mỗi bản thay thế nằm dưới `META-INF/versions/N/` với `N` là số nguyên từ 9 trở lên.
- [ ] Đường dẫn sau `<N>/` khớp đường dẫn logic của bản nền.
- [ ] Mỗi source root được biên dịch bằng `javac --release N` tương ứng.
- [ ] Class thay thế giữ binary API tương thích với bản nền.
- [ ] Resource thay thế nằm đúng package/resource path.
- [ ] `jar --list` cho thấy cấu trúc mong đợi.
- [ ] `jar --validate` kết thúc thành công.
- [ ] Đã kiểm tra runtime chọn bản mới nhất phù hợp và fallback về bản nền.
- [ ] Nếu JAR được ký, chữ ký được tạo sau khi hoàn tất mọi entry.

## Tài liệu tham khảo

1. [JEP 238: Multi-Release JAR Files](https://openjdk.org/jeps/238), mục tiêu, cấu trúc và quy tắc chọn entry theo runtime version.
2. [The jar Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html), tùy chọn `--release`, tạo và kiểm tra JAR.
3. [The javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html), tùy chọn `--release` khi biên dịch theo từng phiên bản Java.
4. [Java API — JarFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/jar/JarFile.html), đọc manifest và hành vi versioning của multi-release JAR.