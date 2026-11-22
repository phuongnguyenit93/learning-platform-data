# Đọc thông tin phiên bản qua JarFile và JarEntry

JAR đa phiên bản (multi-release JAR) cho phép một thư viện đóng gói nhiều implementation của cùng một lớp hoặc tài nguyên trong một file JAR. JVM chọn phiên bản phù hợp với Java runtime đang sử dụng. Cơ chế này giúp một thư viện dùng API mới trên JDK mới, đồng thời giữ implementation nền cho các runtime cũ hơn.

Từ Java 9, **JarFile** có API để mở JAR theo một phiên bản Java cụ thể, kiểm tra JAR có phải multi-release hay không và tra cứu entry theo phiên bản đã chọn. **JarEntry** mô tả một file bên trong JAR, gồm tên entry, kích thước, thời gian, CRC và các metadata khác.

Cần phân biệt ba loại thông tin:

- **Phiên bản runtime dùng để đọc JAR:** được cấu hình qua **Runtime.Version** và có thể đọc lại bằng **JarFile.getVersion()**.
- **Phiên bản vật lý của entry được chọn:** từ Java 10, có thể xem bằng **JarEntry.getRealName()**.
- **Phiên bản phát hành của thư viện:** thường được khai báo riêng trong manifest, ví dụ **Implementation-Version**.

Ba giá trị này có ý nghĩa khác nhau. Không dùng **JarFile.getVersion()** để đọc phiên bản phát hành của thư viện.

## 1. Cấu trúc của multi-release JAR

Một multi-release JAR có các entry nền và các entry thay thế theo phiên bản Java:

~~~text
sample.jar
├── META-INF/
│   └── MANIFEST.MF
├── demo/
│   └── version.txt
└── META-INF/
    └── versions/
        ├── 9/
        │   └── demo/
        │       └── version.txt
        └── 17/
            └── demo/
                └── version.txt
~~~

Manifest phải có thuộc tính:

~~~text
Manifest-Version: 1.0
Multi-Release: true
Implementation-Version: 3.2.1
~~~

Ý nghĩa:

- **demo/version.txt** là entry nền, dùng cho runtime không chọn được entry thay thế.
- **META-INF/versions/9/demo/version.txt** là entry dành cho Java 9 trở lên.
- **META-INF/versions/17/demo/version.txt** là entry dành cho Java 17 trở lên.
- **Multi-Release: true** đánh dấu JAR hỗ trợ cơ chế đa phiên bản.
- **Implementation-Version** là chuỗi phiên bản phát hành do nhà phát triển thư viện khai báo.

Khi mở JAR theo target version V, Java chọn entry có phiên bản cao nhất không vượt quá V. Nếu không có entry thay thế phù hợp, entry nền được sử dụng.

Ví dụ với JAR có entry nền, phiên bản 9 và phiên bản 17:

| Target version | Entry được chọn | Nội dung |
|---:|---|---|
| 8 | Entry nền | base |
| 9 | Phiên bản 9 | version-9 |
| 17 | Phiên bản 17 | version-17 |
| 24 | Phiên bản 17 | version-17 |

Runtime 24 vẫn chọn entry phiên bản 17 vì đây là phiên bản cao nhất được đóng gói mà không vượt quá 24.

## 2. JarFile và Runtime.Version từ Java 9

Java 9 bổ sung constructor nhận **Runtime.Version**:

~~~java
JarFile(File file,
        boolean verify,
        int mode,
        Runtime.Version version)
~~~

Các tham số:

- **file:** file JAR cần mở.
- **verify:** bật hoặc tắt kiểm tra chữ ký JAR.
- **mode:** chế độ mở của ZipFile, thường dùng **ZipFile.OPEN_READ**.
- **version:** phiên bản Java mà JarFile dùng để tạo góc nhìn multi-release.

Ví dụ:

~~~java
Runtime.Version target = Runtime.Version.parse("17");

try (JarFile jar = new JarFile(
        new File("sample.jar"),
        true,
        ZipFile.OPEN_READ,
        target)) {
    // Đọc JAR theo góc nhìn của Java 17.
}
~~~

**Runtime.Version.parse("17")** tạo đối tượng mô tả phiên bản Java 17. Việc chỉ định rõ target giúp kiểm thử tái lập được trên máy có runtime mới hơn.

Nếu muốn dùng phiên bản runtime hiện tại, có thể lấy:

~~~java
Runtime.Version target = JarFile.runtimeVersion();
~~~

Để luôn đọc entry nền, dùng:

~~~java
Runtime.Version target = JarFile.baseVersion();
~~~

**baseVersion()** đại diện cho góc nhìn nền của JAR, tương ứng phiên bản 8. Hai phương thức **runtimeVersion()** và **baseVersion()** thuộc API Java 9.

### 2.1. getVersion()

~~~java
Runtime.Version version = jar.getVersion();
~~~

**getVersion()** trả về phiên bản mà JarFile đang được cấu hình để xử lý. Nó cho biết góc nhìn phiên bản của lần mở JAR.

Ví dụ, khi tạo JarFile với target 24:

~~~java
JarFile jar = new JarFile(
    file, true, ZipFile.OPEN_READ,
    Runtime.Version.parse("24"));

System.out.println(jar.getVersion());
~~~

Kết quả là **24**, kể cả khi entry được chọn thực tế nằm trong thư mục **META-INF/versions/17**.

Vì vậy, **getVersion() không cho biết entry cụ thể được lấy từ thư mục phiên bản nào**. Nó trả về target version của JarFile.

### 2.2. isMultiRelease()

~~~java
boolean multiRelease = jar.isMultiRelease();
~~~

Phương thức này cho biết manifest của JAR có khai báo **Multi-Release: true** hay không.

Nên kiểm tra giá trị này khi chương trình cần phân biệt JAR thông thường với JAR đa phiên bản:

~~~java
if (!jar.isMultiRelease()) {
    System.out.println("This JAR is not multi-release.");
}
~~~

Nếu JAR không được đánh dấu multi-release, các thư mục dưới **META-INF/versions/** không được sử dụng như các entry thay thế trong góc nhìn versioned.

### 2.3. getJarEntry()

~~~java
JarEntry entry = jar.getJarEntry("demo/version.txt");
~~~

Khi JarFile được mở với target version và JAR có **Multi-Release: true**, phương thức này tra cứu entry theo góc nhìn phiên bản đã chọn.

Tên truyền vào là tên logic của entry, không phải đường dẫn vật lý dưới **META-INF/versions/**.

Ví dụ:

- Tra cứu **demo/version.txt** với target 9 sẽ đọc entry phiên bản 9 nếu entry đó tồn tại.
- Tra cứu cùng tên với target 17 sẽ đọc entry phiên bản 17 nếu có.
- Với target 24, entry phiên bản 17 tiếp tục được chọn nếu không có phiên bản mới hơn phù hợp.

Nếu entry không tồn tại trong góc nhìn đã chọn, kết quả là **null**. Hãy kiểm tra null trước khi đọc nội dung.

## 3. Đọc metadata qua JarEntry

**JarEntry** đại diện cho một entry trong JAR. Sau khi lấy entry bằng **getJarEntry()**, có thể đọc metadata trước khi lấy nội dung.

Các phương thức thường dùng:

| Phương thức | Thông tin |
|---|---|
| **getName()** | Tên logic của entry trong góc nhìn đang đọc |
| **getSize()** | Kích thước nội dung chưa nén, tính bằng byte |
| **getCompressedSize()** | Kích thước sau nén |
| **getCrc()** | Giá trị CRC của entry |
| **getMethod()** | Phương thức lưu trữ, ví dụ STORED hoặc DEFLATED |
| **getTime()** | Thời điểm sửa đổi entry |
| **isDirectory()** | Entry có phải thư mục không |
| **getAttributes()** | Các manifest attributes riêng của entry |

Ví dụ:

~~~java
System.out.println("name=" + entry.getName());
System.out.println("size=" + entry.getSize());
System.out.println("compressed-size=" + entry.getCompressedSize());
System.out.println("crc=" + entry.getCrc());
System.out.println("method=" + entry.getMethod());
System.out.println("time=" + entry.getTime());
~~~

**getSize()** và **getCompressedSize()** trả về số byte. Không nhầm kích thước byte với số ký tự khi entry chứa văn bản UTF-8.

Một số metadata có thể chưa xác định và trả về giá trị âm, tùy entry và nguồn dữ liệu. Không nên dùng một giá trị metadata đơn lẻ làm bằng chứng nội dung đã đọc thành công.

### 3.1. Đọc manifest và phiên bản phát hành

**JarFile.getVersion()** là target version dùng để chọn entry. Nếu cần đọc phiên bản phát hành của thư viện, hãy đọc manifest:

~~~java
Manifest manifest = jar.getManifest();

String implementationVersion = manifest == null
    ? null
    : manifest.getMainAttributes().getValue(
        Attributes.Name.IMPLEMENTATION_VERSION);

System.out.println("implementation-version="
    + implementationVersion);
~~~

Ví dụ manifest có:

~~~text
Implementation-Version: 3.2.1
~~~

thì kết quả là:

~~~text
implementation-version=3.2.1
~~~

Đây là phiên bản do nhà phát triển khai báo. Nó không tự động thay đổi theo JDK đang chạy.

Nếu cần đọc thuộc tính riêng của một entry, dùng:

~~~java
Attributes attributes = entry.getAttributes();

String buildVariant = attributes == null
    ? null
    : attributes.getValue("Build-Variant");
~~~

Thuộc tính này đến từ phần tương ứng của manifest. Nếu manifest không có section cho entry, **getAttributes()** có thể trả về null.

### 3.2. Đọc nội dung entry

Có thể lấy InputStream từ JarFile:

~~~java
try (InputStream input = jar.getInputStream(entry)) {
    byte[] bytes = input.readAllBytes();
    String content = new String(bytes, StandardCharsets.UTF_8);
    System.out.println(content);
}
~~~

Dùng đúng charset của nội dung. Ví dụ trên giả định file được mã hóa UTF-8.

Nên dùng try-with-resources cho cả **JarFile** và **InputStream** để đóng file handle và stream khi hoàn tất.

## 4. Ví dụ Java 9 hoàn chỉnh

Ví dụ sau chỉ dùng API có sẵn từ Java 9. Nó mở một multi-release JAR theo target version, đọc metadata, đọc phiên bản phát hành trong manifest và lấy nội dung entry được chọn.

Tệp **src/InspectJar.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;
import java.util.zip.ZipFile;

public final class InspectJar {
    public static void main(String[] args) throws IOException {
        Runtime.Version target =
            Runtime.Version.parse(args[1]);

        try (JarFile jar = new JarFile(
                new File(args[0]),
                true,
                ZipFile.OPEN_READ,
                target)) {

            System.out.println(
                "configured-version=" + jar.getVersion());

            System.out.println(
                "multi-release=" + jar.isMultiRelease());

            Manifest manifest = jar.getManifest();

            String implementationVersion = manifest == null
                ? null
                : manifest.getMainAttributes().getValue(
                    Attributes.Name.IMPLEMENTATION_VERSION);

            System.out.println(
                "implementation-version=" + implementationVersion);

            JarEntry entry = jar.getJarEntry("demo/version.txt");

            if (entry == null) {
                throw new IllegalStateException(
                    "Missing entry: demo/version.txt");
            }

            System.out.println("entry-name=" + entry.getName());
            System.out.println("entry-size=" + entry.getSize());

            try (InputStream input = jar.getInputStream(entry)) {
                String content = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

                System.out.println("entry-content=" + content);
            }
        }
    }
}
~~~

### 4.1. Tạo JAR mẫu

Tạo cấu trúc thư mục:

~~~text
base/
└── demo/
    └── version.txt

v9/
└── META-INF/
    └── versions/
        └── 9/
            └── demo/
                └── version.txt

v17/
└── META-INF/
    └── versions/
        └── 17/
            └── demo/
                └── version.txt
~~~

Nội dung các file:

~~~text
base/demo/version.txt:
base

v9/META-INF/versions/9/demo/version.txt:
version-9

v17/META-INF/versions/17/demo/version.txt:
version-17
~~~

Tạo file **manifest.mf**:

~~~text
Manifest-Version: 1.0
Multi-Release: true
Implementation-Version: 3.2.1
~~~

Tạo JAR từ thư mục gốc của dự án:

~~~bash
jar --create --file sample.jar --manifest manifest.mf   -C base .   -C v9 META-INF/versions/9   -C v17 META-INF/versions/17
~~~

Lệnh này đóng gói entry nền và hai entry thay thế vào cùng một JAR.

### 4.2. Biên dịch và chạy

Biên dịch với API Java 9:

~~~bash
javac --release 9 -d out src/InspectJar.java
~~~

Chạy chương trình với target version 17:

~~~bash
java -cp out InspectJar sample.jar 17
~~~

Kết quả stdout:

~~~text
configured-version=17
multi-release=true
implementation-version=3.2.1
entry-name=demo/version.txt
entry-size=10
entry-content=version-17
~~~

Kết quả cho thấy:

- JarFile được cấu hình theo target version 17.
- JAR được đánh dấu multi-release.
- Phiên bản phát hành trong manifest là 3.2.1.
- Entry logic **demo/version.txt** được chọn từ phiên bản 17.
- Nội dung thực tế đọc được là **version-17**.

Có thể thay tham số target thành 8, 9 hoặc 24 để quan sát lựa chọn khác nhau. Với JAR mẫu này, target 8 đọc **base**, target 9 đọc **version-9**, còn target 24 vẫn đọc **version-17**.

## 5. API Java 10+: xem tên vật lý và versioned stream

Java 10 bổ sung hai API hữu ích khi kiểm tra multi-release JAR:

- **JarEntry.getRealName()** trả về tên vật lý của entry trong file JAR.
- **JarFile.versionedStream()** trả về stream các entry trong góc nhìn đa phiên bản đã chọn.

Ví dụ:

~~~java
try (JarFile jar = new JarFile(
        file,
        true,
        ZipFile.OPEN_READ,
        Runtime.Version.parse("24"))) {

    JarEntry entry = jar.getJarEntry("demo/version.txt");

    System.out.println("logical-name=" + entry.getName());
    System.out.println("physical-name=" + entry.getRealName());

    JarEntry selected = jar.versionedStream()
        .filter(candidate ->
            candidate.getName().equals("demo/version.txt"))
        .findFirst()
        .orElseThrow();

    System.out.println(
        "versioned-stream-real-name=" + selected.getRealName());
}
~~~

Với JAR mẫu có entry phiên bản 9 và 17, kết quả trên target 24:

~~~text
logical-name=demo/version.txt
physical-name=META-INF/versions/17/demo/version.txt
versioned-stream-real-name=META-INF/versions/17/demo/version.txt
~~~

Tên logic là tên ứng dụng dùng để tra cứu. Tên vật lý cho biết file nào trong archive đã được chọn.

### 5.1. Phân biệt stream() và versionedStream()

Từ Java 10:

- **stream()** duyệt các entry vật lý có trong archive, gồm entry nền và các entry dưới **META-INF/versions/**.
- **versionedStream()** duyệt góc nhìn hiệu lực của JAR theo target version; các entry thay thế được chọn cho tên logic tương ứng.

Ví dụ, với JAR mẫu, **stream()** có thể liệt kê:

~~~text
demo/version.txt
META-INF/versions/9/demo/version.txt
META-INF/versions/17/demo/version.txt
~~~

Trong khi **versionedStream()** chỉ cung cấp entry được chọn cho tên logic **demo/version.txt** trong góc nhìn target 24, tức entry phiên bản 17.

### 5.2. Lưu ý tương thích Java 9

**getRealName()** và **versionedStream()** không thuộc API Java 9. Cả hai được bổ sung từ Java 10.

Nếu dự án cần biên dịch với **--release 9**, hãy dùng các API Java 9 như:

- Constructor JarFile nhận **Runtime.Version**.
- **JarFile.getVersion()**.
- **JarFile.isMultiRelease()**.
- **JarFile.getJarEntry()**.
- **JarFile.getManifest()**.

Không gọi **getRealName()** hoặc **versionedStream()** trong source code có target Java 9. Có thể đặt phần kiểm tra nâng cao này trong source set hoặc module yêu cầu Java 10 trở lên.

## 6. Những nhầm lẫn thường gặp

### 6.1. Nhầm getVersion() với Implementation-Version

**jar.getVersion()** trả về target version mà JarFile đang xử lý.

**Implementation-Version** là thuộc tính manifest do nhà phát triển thư viện khai báo.

Ví dụ target Java 24 có thể đọc một entry từ thư mục phiên bản 17, trong khi manifest vẫn ghi Implementation-Version 3.2.1.

### 6.2. Nhầm tên logic với tên vật lý

**entry.getName()** trong góc nhìn versioned có thể là:

~~~text
demo/version.txt
~~~

Từ Java 10, **entry.getRealName()** có thể trả về:

~~~text
META-INF/versions/17/demo/version.txt
~~~

Đây là hai cách biểu diễn cùng entry được chọn, không phải hai file nội dung khác nhau trong góc nhìn ứng dụng.

### 6.3. Quên thuộc tính Multi-Release

Chỉ tạo thư mục **META-INF/versions/9/** hoặc **META-INF/versions/17/** là chưa đủ. Manifest phải có:

~~~text
Multi-Release: true
~~~

Nếu thiếu thuộc tính này, runtime không xử lý các entry đó như implementation thay thế của multi-release JAR.

### 6.4. Dùng sai tên khi tra cứu

Khi dùng **getJarEntry()** để lấy entry theo versioned view, truyền tên logic:

~~~java
jar.getJarEntry("demo/version.txt");
~~~

Không truyền đường dẫn vật lý có tiền tố **META-INF/versions/** nếu mục tiêu là yêu cầu JarFile tự chọn phiên bản phù hợp.

### 6.5. Không kiểm tra entry null

Nếu JAR không có entry cần đọc trong góc nhìn đã chọn, **getJarEntry()** trả về null. Hãy kiểm tra trước khi gọi **getInputStream()** hoặc đọc metadata.

### 6.6. Quên đóng JarFile và stream

JarFile giữ tài nguyên file. Hãy dùng try-with-resources để tránh giữ file handle ngoài ý muốn, đặc biệt trên Windows khi ứng dụng cần thay thế hoặc xóa JAR sau đó.

### 6.7. Hiểu sai metadata chữ ký

Nếu cần kiểm tra **getCertificates()** hoặc **getCodeSigners()**, hãy mở JarFile với xác minh chữ ký và đọc hết nội dung entry. Thông tin chứng thư/người ký chỉ sẵn sàng sau khi entry đã được đọc và xác minh đầy đủ. Chỉ mở JAR hoặc lấy JarEntry chưa đủ để kết luận entry đã được xác minh.

## 7. Checklist khi đọc phiên bản và metadata của JAR

- Xác định đang cần target version của JarFile hay phiên bản phát hành của thư viện.
- Kiểm tra **JarFile.isMultiRelease()**.
- Chọn target rõ ràng bằng **Runtime.Version.parse()** khi cần kiểm thử tái lập.
- Dùng **JarFile.getVersion()** để ghi nhận góc nhìn phiên bản đã cấu hình.
- Dùng tên logic với **JarFile.getJarEntry()** để lấy entry phù hợp.
- Kiểm tra null trước khi đọc entry.
- Dùng **JarEntry.getSize()**, **getCrc()**, **getMethod()** và metadata liên quan khi cần kiểm tra file.
- Dùng **JarFile.getManifest()** để đọc **Implementation-Version**.
- Dùng **JarEntry.getRealName()** và **JarFile.versionedStream()** khi ứng dụng yêu cầu Java 10 trở lên.
- Đóng JarFile và InputStream bằng try-with-resources.
- Nếu kiểm tra chữ ký, bật verify và đọc toàn bộ entry trước khi lấy certificates/signers.

**Nguyên tắc sử dụng:** JarFile quyết định góc nhìn phiên bản của multi-release JAR; JarEntry mô tả entry được chọn. Từ Java 9, có thể chọn target version và đọc entry tương ứng. Từ Java 10, có thêm **getRealName()** và **versionedStream()** để quan sát tên vật lý và góc nhìn versioned rõ hơn. Phiên bản runtime, phiên bản vật lý của entry và phiên bản phát hành trong manifest là ba thông tin riêng biệt.