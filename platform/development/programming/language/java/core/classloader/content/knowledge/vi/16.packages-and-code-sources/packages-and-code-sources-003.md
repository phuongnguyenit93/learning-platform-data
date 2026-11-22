# Package sealing và thông tin manifest

## 1. Package sealing giải quyết vấn đề gì?

Một ứng dụng Java có thể đưa nhiều file JAR vào cùng đường tìm kiếm của ClassLoader. Nếu hai JAR chứa các class có **cùng package name**, loader đôi khi có thể nạp một class từ JAR A và class khác từ JAR B. Điều này thường được gọi là **split package trên classpath**.

Ví dụ:

~~~text
a.jar
└── demo/locked/Anchor.class

b.jar
└── demo/locked/Other.class
~~~

Nếu không có quy tắc bổ sung, một `URLClassLoader` dùng cả hai JAR có thể nạp `demo.locked.Anchor` từ A và `demo.locked.Other` từ B; cả hai có chung tên package và cùng defining loader.

**Package sealing** là cơ chế của định dạng JAR và loader hỗ trợ manifest nhằm ràng buộc: **các class thuộc cùng một sealed package phải đến từ cùng nguồn JAR/code source**. Khi một loader cố định nghĩa class cùng sealed package từ nguồn không khớp, implementation như `URLClassLoader` sẽ báo `SecurityException` với nội dung liên quan đến *sealing violation*.

Cần phân biệt ngay:

- **Package sealing không phải class visibility**: `public`, `private`, package-private, JPMS `exports`/`opens` vẫn được kiểm tra theo quy tắc riêng.
- **Package sealing không phải chữ ký số JAR**: `Sealed: true` không ký bytecode, không xác thực người phát hành.
- **Package sealing không phải công cụ khóa version dependency tự động**: nó phát hiện một số trường hợp class cùng package đến từ các nguồn khác nhau.
- **Package sealing được xét theo loader định nghĩa package**. Hai ClassLoader độc lập vẫn có thể định nghĩa các package cùng tên riêng biệt, không bị gộp thành một package trên toàn JVM.

Trong Java 17, `URLClassLoader` sử dụng thông tin `Manifest` khi tạo `Package` và khi kiểm tra việc nạp các class tiếp theo. Đây là bối cảnh của bài.

## 2. Tên package, runtime package và nơi xuất phát bytecode

Ba khái niệm có liên quan nhưng không đồng nhất:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Package name | `demo.locked` | Tên package viết trong source Java |
| Runtime package | `demo.locked` trong defining loader cụ thể (và module liên quan) | Quan trọng cho định danh và quyền truy cập package-private |
| Code source URL | `file:/.../a.jar` | Nơi loader lấy bytecode, dùng trong kiểm tra sealing |

Hai class có cùng package name nhưng được **hai loader khác nhau** định nghĩa không tự động nằm trong cùng runtime package. Ngược lại, nếu cùng `URLClassLoader` định nghĩa chúng từ hai JAR khác nhau, sealing của package có thể ngăn sự pha trộn bytecode từ hai code source.

**Thứ tự quan trọng:** `Package` metadata thường được xác định tại thời điểm package được định nghĩa lần đầu trong loader. Một class được nạp sớm từ JAR có thể thiết lập package sealed/unsealed; class sau phải tương thích với tình trạng đã thiết lập.

Tài liệu JAR nêu rằng sealed package buộc class trong package đó xuất phát từ cùng JAR. Trong triển khai `URLClassLoader`, so sánh gắn với **URL code source** của package.

## 3. Manifest là gì và lưu ở đâu?

Một JAR thông thường có tệp metadata:

~~~text
META-INF/MANIFEST.MF
~~~

Đây là file văn bản có **main section** và có thể có các **named sections**. Thông tin quan trọng trong bài:

| Attribute | Mức áp dụng | Tác dụng |
|---|---|---|
| `Manifest-Version` | Main | Phiên bản định dạng manifest, thường `1.0` |
| `Sealed` | Main hoặc section package | Quy định package sealed hay không |
| `Specification-Title` | Main hoặc package | Tên đặc tả mà package triển khai |
| `Specification-Version` | Main hoặc package | Phiên bản đặc tả |
| `Specification-Vendor` | Main hoặc package | Bên cung cấp đặc tả |
| `Implementation-Title` | Main hoặc package | Tên implementation |
| `Implementation-Version` | Main hoặc package | Phiên bản implementation |
| `Implementation-Vendor` | Main hoặc package | Nhà cung cấp implementation |
| `Main-Class` | Main | Entry point cho JAR chạy với launcher thích hợp; **không phải sealing** |
| `Class-Path` | Main | Có thể tham gia mở rộng đường tìm class trong một số cách chạy/loader; **không phải sealing** |

Ví dụ main section:

~~~text
Manifest-Version: 1.0
Sealed: true

~~~

Với manifest này, **các package của JAR được sealed mặc định**, trừ package có named section ghi đè. Để chỉ sealed một package, đặt `Sealed: true` trong section riêng:

~~~text
Manifest-Version: 1.0

Name: demo/locked/
Sealed: true

~~~

**Chú ý đường dẫn:** `Name: demo/locked/` có dấu `/` cuối, đại diện cho package `demo.locked`. Nó không phải `Name: demo.locked` và không phải tên file `Anchor.class`.

Giữa main section và named section phải có **dòng trống**. Mỗi section cần kết thúc đúng cú pháp manifest; khi tự tạo file nên có newline cuối file. File manifest tuân quy tắc dòng/continuation của đặc tả JAR, không nên tự nối thành một dòng rất dài.

## 4. Quy tắc ưu tiên `Sealed`: toàn JAR và từng package

Các trường hợp:

**A. Không khai báo `Sealed`:**

~~~text
Manifest-Version: 1.0

~~~

Mặc định package của JAR **không sealed** nếu không có section riêng quy định.

**B. Khai báo ở main section:**

~~~text
Manifest-Version: 1.0
Sealed: true

~~~

Tất cả package trong JAR mặc định sealed.

**C. Main sealed, một package ghi đè unsealed:**

~~~text
Manifest-Version: 1.0
Sealed: true

Name: demo/open/
Sealed: false

~~~

Package `demo.open` không sealed, còn các package khác vẫn sealed theo main section.

**D. Main không sealed, một package ghi đè sealed:**

~~~text
Manifest-Version: 1.0
Sealed: false

Name: demo/locked/
Sealed: true

~~~

Chỉ `demo.locked` được sealed theo section này; các package khác vẫn unsealed nếu không có override khác.

Giá trị `Sealed` là `true` hoặc `false`, không phân biệt chữ hoa/thường. Một named section cụ thể **ưu tiên hơn** giá trị ở main section. Các thuộc tính phiên bản và vendor cũng có thể có giá trị riêng theo package.

**Lưu ý:** Sealing không áp dụng cho unnamed package; class muốn thuộc package sealed cần được khai báo trong một package có tên.

## 5. Bài thực hành Java 17+: A sealed, B khác nguồn, package open vẫn hoạt động

Ta sẽ tạo hai JAR từ bốn class:

~~~text
sealing-demo/
├── a-src/
│   └── demo/
│       ├── locked/Anchor.java
│       └── open/One.java
├── b-src/
│   └── demo/
│       ├── locked/Other.java
│       └── open/Two.java
├── host-src/
│   └── SealingDemo.java
└── manifests/
    ├── a.mf
    └── b.mf
~~~

`a.jar` sealed **chỉ** package `demo.locked` và gắn thông tin phiên bản. `b.jar` không sealed. Khi một `URLClassLoader` nhìn cả A và B:

- Nạp `Anchor` từ A trước → package `demo.locked` được tạo trong trạng thái sealed tại A.
- Nạp `Other` từ B sau → `SecurityException` do sealing violation.
- Package khác tên `demo.open` không sealed nên `One` của A và `Two` của B có thể cùng được loader đó định nghĩa.
- Nếu nạp `Other` từ B trước, package `demo.locked` bắt đầu ở trạng thái unsealed; sau đó cố nạp `Anchor` từ JAR A tuyên bố sealing → cũng là sealing violation.

Ta dùng **các class có tên khác nhau** trong cùng package để loại bỏ sự nhầm lẫn với tình huống hai JAR có đúng cùng FQCN và chỉ một phiên bản được tìm thấy trước.

### 5.1. Class của JAR A: `Anchor`

Tệp **`a-src/demo/locked/Anchor.java`**:

~~~java
package demo.locked;

public final class Anchor {
    private Anchor() {
    }

    public static String origin() {
        return "ANCHOR_A";
    }
}
~~~

Tệp **`a-src/demo/open/One.java`**:

~~~java
package demo.open;

public final class One {
    private One() {
    }

    public static String origin() {
        return "ONE_A";
    }
}
~~~

### 5.2. Class của JAR B: `Other`

Tệp **`b-src/demo/locked/Other.java`**:

~~~java
package demo.locked;

public final class Other {
    private Other() {
    }

    public static String origin() {
        return "OTHER_B";
    }
}
~~~

Tệp **`b-src/demo/open/Two.java`**:

~~~java
package demo.open;

public final class Two {
    private Two() {
    }

    public static String origin() {
        return "TWO_B";
    }
}
~~~

Bốn class chỉ phụ thuộc Java chuẩn. Host sẽ nạp bằng tên chuỗi và reflection; **không import** bất kỳ class `demo.locked.*` hay `demo.open.*` để tránh ứng dụng chủ vô tình đưa chúng vào defining loader khác.

### 5.3. Manifest của A với metadata riêng cho package

Tệp **`manifests/a.mf`** (tạo với newline cuối):

~~~text
Manifest-Version: 1.0
Implementation-Title: Example A Archive

Name: demo/locked/
Sealed: true
Specification-Title: Demo Package Contract
Specification-Version: 1.0
Implementation-Title: Locked Package A
Implementation-Version: 2.1.0

~~~

Giải thích:

- Không có `Sealed: true` ở main section, vì ta không muốn sealed `demo.open`.
- Section `Name: demo/locked/` sealed **chính package đó**.
- `Specification-Title` và `Specification-Version` mô tả đặc tả của package.
- `Implementation-Title` và `Implementation-Version` ở section package cung cấp metadata khi loader định nghĩa `demo.locked` từ A.
- `Implementation-Title: Example A Archive` ở main section có thể áp dụng cho package khác, nhưng bản `Locked Package A` trong named section **ghi đè cho `demo.locked`**.

Tệp **`manifests/b.mf`**:

~~~text
Manifest-Version: 1.0

~~~

Không có `Sealed` hoặc version metadata cho `demo.locked` trong B, nên khi B là nguồn định nghĩa package trước, package được xác lập là **unsealed**.

### 5.4. Host kiểm tra `Package` và nạp class trùng package

Tệp **`host-src/SealingDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SealingDemo {
    private SealingDemo() {
    }

    private static boolean sealingViolation(
            ClassLoader loader, String name) {
        try {
            loader.loadClass(name);
            return false;
        } catch (SecurityException expected) {
            return true;
        } catch (ClassNotFoundException unexpected) {
            throw new IllegalStateException(
                    "Required class missing: " + name, unexpected);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: SealingDemo <a.jar> <b.jar>");
        }

        Path a = Path.of(args[0]).toAbsolutePath().normalize();
        Path b = Path.of(args[1]).toAbsolutePath().normalize();

        if (!Files.isRegularFile(a) || !Files.isRegularFile(b)) {
            throw new IllegalArgumentException("Both JARs must exist");
        }

        URL aUrl = a.toUri().toURL();
        URL bUrl = b.toUri().toURL();

        // Các class trong A/B chỉ phụ thuộc java.base.
        // Platform loader không giữ demo.locked/demo.open của host.
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader combined = new URLClassLoader(
                    new URL[] {aUrl, bUrl}, parent);
             URLClassLoader reverse = new URLClassLoader(
                    new URL[] {bUrl, aUrl}, parent);
             URLClassLoader aOnly = new URLClassLoader(
                    new URL[] {aUrl}, parent);
             URLClassLoader bOnly = new URLClassLoader(
                    new URL[] {bUrl}, parent)) {

            Class<?> anchor = combined.loadClass(
                    "demo.locked.Anchor");
            Package pkg = anchor.getPackage();

            System.out.println("Anchor sealed: " + pkg.isSealed());
            System.out.println("Sealed at A URL: "
                    + pkg.isSealed(aUrl));
            System.out.println("Sealed at B URL: "
                    + pkg.isSealed(bUrl));
            System.out.println("Spec title: "
                    + pkg.getSpecificationTitle());
            System.out.println("Spec version: "
                    + pkg.getSpecificationVersion());
            System.out.println("Impl title: "
                    + pkg.getImplementationTitle());
            System.out.println("Impl version: "
                    + pkg.getImplementationVersion());

            System.out.println("A then B violation: "
                    + sealingViolation(combined,
                            "demo.locked.Other"));

            Class<?> one = combined.loadClass("demo.open.One");
            Class<?> two = combined.loadClass("demo.open.Two");
            System.out.println("Open package unsealed: "
                    + !one.getPackage().isSealed());
            System.out.println("Open from same loader: "
                    + (one.getClassLoader()
                    == two.getClassLoader()));

            Class<?> firstB = reverse.loadClass(
                    "demo.locked.Other");
            System.out.println("B first unsealed: "
                    + !firstB.getPackage().isSealed());
            System.out.println("B then A violation: "
                    + sealingViolation(reverse,
                            "demo.locked.Anchor"));

            Class<?> onlyA = aOnly.loadClass(
                    "demo.locked.Anchor");
            Class<?> onlyB = bOnly.loadClass(
                    "demo.locked.Other");
            System.out.println("Separate loaders succeed: "
                    + (onlyA != null && onlyB != null));
            System.out.println("Same name package object: "
                    + (onlyA.getPackage() == onlyB.getPackage()));
        }
    }
}
~~~

Chương trình tạo **bốn `URLClassLoader` riêng** để mỗi tình huống có trạng thái package độc lập. Điều này tránh việc case nạp A trước vô tình ảnh hưởng case B trước.

**Không dùng application/system loader làm parent trong ví dụ** vì host không cần API dùng chung từ JAR; chọn platform loader giúp đảm bảo việc thử nghiệm không bị class `demo.locked.*` ở application classpath che trước. Trong hệ plugin thực tế cần interface host, parent phải là loader nhìn thấy đúng shared API — không tự động chọn platform loader cho mọi trường hợp.

### 5.5. Biên dịch và đóng gói

Yêu cầu **JDK 17+**, chạy từ thư mục `sealing-demo/`.

**Bash (Linux, macOS hoặc Git Bash):**

~~~bash
mkdir -p build/a build/b build/host dist

javac -encoding UTF-8 -d build/a \
  a-src/demo/locked/Anchor.java \
  a-src/demo/open/One.java

javac -encoding UTF-8 -d build/b \
  b-src/demo/locked/Other.java \
  b-src/demo/open/Two.java

javac -encoding UTF-8 -d build/host \
  host-src/SealingDemo.java

jar --create --file dist/a.jar \
  --manifest manifests/a.mf -C build/a .

jar --create --file dist/b.jar \
  --manifest manifests/b.mf -C build/b .

java -cp build/host SealingDemo dist/a.jar dist/b.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/a,build/b,build/host,dist | Out-Null

javac -encoding UTF-8 -d build/a a-src/demo/locked/Anchor.java a-src/demo/open/One.java

javac -encoding UTF-8 -d build/b b-src/demo/locked/Other.java b-src/demo/open/Two.java

javac -encoding UTF-8 -d build/host host-src/SealingDemo.java

jar --create --file dist/a.jar --manifest manifests/a.mf -C build/a .

jar --create --file dist/b.jar --manifest manifests/b.mf -C build/b .

java -cp build/host SealingDemo dist/a.jar dist/b.jar
~~~

Trước khi chạy, kiểm tra JAR:

~~~bash
jar --list --file dist/a.jar
jar --list --file dist/b.jar
jar --extract --file dist/a.jar META-INF/MANIFEST.MF
~~~

Lệnh `jar --extract` ghi `META-INF/MANIFEST.MF` vào thư mục hiện tại, nên **không bắt buộc chạy lệnh extract** nếu chỉ cần kiểm tra logic; có thể kiểm tra manifest bằng công cụ xem nội dung ZIP/JAR. Nếu chạy extract, hãy thực hiện trong thư mục kiểm tra riêng, tránh đè lên file cùng tên của dự án.

Các entry chính cần có:

~~~text
a.jar:
  demo/locked/Anchor.class
  demo/open/One.class
  META-INF/MANIFEST.MF

b.jar:
  demo/locked/Other.class
  demo/open/Two.class
  META-INF/MANIFEST.MF
~~~

Việc dùng `jar --manifest` bảo đảm metadata được đóng trong JAR. Nếu tự tạo JAR không dùng manifest mong muốn, `Package.getImplementationVersion()` có thể là `null` và sealing không có hiệu lực như ví dụ.

### 5.6. Kết quả đầu ra

Với cấu trúc trên, không có class trùng từ parent và JDK 17 `URLClassLoader` chuẩn:

~~~text
Anchor sealed: true
Sealed at A URL: true
Sealed at B URL: false
Spec title: Demo Package Contract
Spec version: 1.0
Impl title: Locked Package A
Impl version: 2.1.0
A then B violation: true
Open package unsealed: true
Open from same loader: true
B first unsealed: true
B then A violation: true
Separate loaders succeed: true
Same name package object: false
~~~

**Đọc kết quả:**

1. `Anchor` đến từ A, manifest A sealed `demo.locked`. `pkg.isSealed()` là `true`.
2. `pkg.isSealed(aUrl)` là `true`, trong khi `pkg.isSealed(bUrl)` là `false` vì hai URL code source khác nhau.
3. `Package` phản ánh đúng `Specification-Title`, `Specification-Version`, `Implementation-Title` và `Implementation-Version` của package section trong A.
4. `combined` thử nạp `Other` từ B vào package đã sealed ở A → `SecurityException` được bắt, in `true`.
5. Package `demo.open` không sealed, nên `One` từ A và `Two` từ B có thể cùng nằm trong **một defining loader**.
6. `reverse` nạp class B trước, định nghĩa `demo.locked` là unsealed; nạp class A có `Sealed: true` sau đó cũng gây vi phạm vì không thể sealed một package đã được định nghĩa unsealed.
7. Hai loader riêng `aOnly`/`bOnly` có **Package object riêng**, dù chuỗi package name giống nhau; không có vi phạm sealing xuyên hai loader độc lập.

Thông điệp quan trọng: **thứ tự class loading**, không chỉ thứ tự URL trên classpath, quyết định class nào tạo package metadata đầu tiên. Class `Anchor` chỉ ở A, `Other` chỉ ở B: khi hỏi `Other` trước, loader có thể đi qua URL A rồi B và lấy class từ B.

## 6. Package metadata được lấy và sử dụng thế nào?

`java.lang.Package` có các phương thức hữu ích:

| API | Ý nghĩa |
|---|---|
| `Class.getPackage()` | Lấy `Package` gắn với runtime class |
| `Package.getName()` | Tên package |
| `Package.isSealed()` | Package có bị sealing không? |
| `Package.isSealed(URL)` | Package có sealed **về URL code source này** không? |
| `Package.getSpecificationTitle()` | Tên đặc tả từ manifest |
| `Package.getSpecificationVersion()` | Phiên bản đặc tả |
| `Package.getSpecificationVendor()` | Nhà cung cấp đặc tả |
| `Package.getImplementationTitle()` | Tên implementation |
| `Package.getImplementationVersion()` | Phiên bản implementation |
| `Package.getImplementationVendor()` | Nhà cung cấp implementation |
| `Package.isCompatibleWith(String)` | Kiểm tra phiên bản đặc tả có đạt mức yêu cầu theo quy tắc số chấm phân tách |

**Không xem `Implementation-Version` là cơ chế enforcement dependency version.** Nó là metadata, có thể vắng mặt hoặc do build pipeline gán. JVM không tự từ chối JAR chỉ vì `Implementation-Version` của package không khớp kỳ vọng ứng dụng.

Với `Package.isCompatibleWith("1.2")`, version specification được diễn giải theo thành phần số không âm ngăn bởi dấu chấm; format không hợp lệ có thể gây `NumberFormatException`. Đây không phải bộ so sánh SemVer đầy đủ như npm/Maven và không nên dùng cho các version string kiểu `"1.2.3-beta"` nếu chưa xử lý riêng.

### Package metadata không đồng nghĩa JAR metadata cho mọi class

Trong một loader, `Package` là metadata gắn với **định nghĩa package**, không phải bản sao độc lập trên mỗi class. Nếu một package unsealed được định nghĩa trước từ JAR A và sau đó class từ JAR B được nạp cùng package, `classB.getPackage()` vẫn có thể trỏ tới `Package` đã được định nghĩa từ A.

Vì vậy **không dùng `getImplementationVersion()` của package làm bằng chứng rằng mọi class trong package đều xuất phát từ cùng JAR**, nhất là khi package unsealed trải trên nhiều nguồn.

Muốn truy vết class cụ thể, xem `Class.getProtectionDomain().getCodeSource().getLocation()` **khi khả dụng**; giá trị có thể null hoặc không có quyền truy cập trong một số môi trường. Đó là thông tin **nguồn bytecode của class**, khác với `Package` metadata.

## 7. Phân biệt package sealing với chữ ký JAR

Một file JAR có thể:

- **Sealed nhưng không signed:** `Sealed: true` chỉ ràng buộc consistency nguồn class trong package, không xác thực nhà phát hành.
- **Signed nhưng không sealed:** Chữ ký dùng để kiểm tra tính toàn vẹn/chứng thư theo cơ chế JAR signing, nhưng package có thể không dùng sealing.
- **Vừa signed vừa sealed:** Hai cơ chế hoạt động với mục đích khác nhau.

Trong cùng một runtime package, các class còn có thể chịu ràng buộc nhất quán về signer/certificate khi định nghĩa class; đây là vấn đề khác với `Sealed`. Đừng sửa lỗi sealing bằng cách tự ý bỏ xác minh chữ ký hoặc chỉnh manifest trong JAR đã ký, vì điều đó có thể làm chữ ký không còn hợp lệ.

**Sealing không phải sandbox.** Một plugin chạy bytecode trong cùng tiến trình vẫn có thể có các quyền của tiến trình. Dùng ranh giới tiến trình/container nếu cần chạy mã không tin cậy.

## 8. Sealing và classloader identity

Điểm dễ nhầm: “Một JVM chỉ được có đúng một class `demo.locked.Anchor` nếu package sealed.” Điều này **sai**.

JVM xác định runtime class dựa trên tên binary **và defining loader**. Hai loader độc lập có thể nạp cùng JAR:

~~~text
(loader A, demo.locked.Anchor)  ≠  (loader B, demo.locked.Anchor)
~~~

Mỗi loader có namespace của mình và có thể định nghĩa `Package` riêng. Sealing bảo đảm tính nhất quán của **một package được loader định nghĩa** với code source tương ứng, chứ không buộc toàn bộ JVM chỉ có một bản class/package cùng tên.

Ngược lại, ngay cả khi **không sealed**, việc một host và plugin tự định nghĩa hai class cùng FQCN có thể gây `ClassCastException`. Vì thế không dùng sealing để giải quyết mọi vấn đề class identity. API dùng chung giữa host và plugin cần được nạp từ một loader chung, còn implementation có thể ở child loader riêng.

## 9. Sealing và thứ tự tìm JAR

Một loader parent-first thường hỏi parent trước. Nếu parent đã có class được yêu cầu, `URLClassLoader` con có thể trả class của parent mà **không tự định nghĩa class đó**; khi ấy trạng thái package sealing của child không quyết định kết quả cho class được parent định nghĩa.

Trong chính URL path của một `URLClassLoader`, thứ tự URL xác định nơi tìm class khi có nhiều nguồn. Nhưng cần phân biệt hai tình huống:

**Cùng một FQCN xuất hiện trong A và B:** URL được tìm thấy trước có thể cung cấp bytecode; class trong URL phía sau bị che. Chỉ riêng sự trùng tên không bắt loader định nghĩa cả hai phiên bản.

**Hai FQCN khác nhau cùng package:** Class A và class B có thể được chọn từ hai JAR khác nhau. Nếu package đã sealed ở một nguồn, việc cố thêm class từ nguồn còn lại sẽ gặp `SecurityException`. Đây là case runnable của bài.

Để kiểm tra vấn đề trong hệ thống thật, đừng chỉ đổi thứ tự `-cp` rồi phỏng đoán. Hãy kiểm tra **defining loader**, **CodeSource URL** nếu có, **manifest sealing attributes**, và **class nào được load trước**.

## 10. Sealing với JPMS, JAR thường và custom loader

**Classpath/unnamed modules:** Tình huống ví dụ sử dụng hai JAR thông thường và `URLClassLoader`, là bối cảnh tiêu biểu cho package sealing trong manifest.

**JPMS named modules:** Việc định nghĩa module/package, readability, `exports`, `opens` và split-package constraints do hệ module quyết định. Không đơn giản áp dụng quy tắc “thêm `Sealed: true` là giải quyết mọi split package trong module path”. Với named modules, thiết kế module/package rõ ràng và tuân module resolution là cách chính.

**Custom ClassLoader:** Nếu bạn tự đọc bytecode qua `Files.readAllBytes` rồi gọi `ClassLoader.defineClass(...)`, Java không tự đọc `META-INF/MANIFEST.MF` của một kho tùy chỉnh để áp dụng chính sách sealing giống `URLClassLoader`. Bạn cần tự định nghĩa `Package` và xử lý metadata/code source/kiểm tra nguồn phù hợp khi triển khai loại loader đó.

`URLClassLoader.definePackage(String name, Manifest man, URL url)` cung cấp API để thiết lập metadata và sealing từ manifest; không nên tự bỏ qua tính nhất quán package khi viết custom loader cho JAR có sealing.

## 11. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có khả năng | Hướng xử lý |
|---|---|---|
| `SecurityException: sealing violation` | Loader định nghĩa class cùng package từ code source khác với package sealed | Kiểm tra manifest, vị trí JAR và class loading order |
| “Can't seal package: already loaded” | Package được xác lập unsealed trước, JAR sau muốn sealed | Loại split package hoặc bảo đảm package đến từ một nguồn |
| `Package.isSealed() == false` dù file manifest có `Sealed: true` | Sai section, sai path `Name`, hoặc package đã được định nghĩa trước từ nguồn khác | Kiểm tra `META-INF/MANIFEST.MF` và package owner |
| `getImplementationVersion() == null` | Không khai báo metadata hoặc loader không chuyển metadata khi define package | Kiểm tra manifest và loader implementation |
| Manifest main sealed làm package khác cũng sealed | `Sealed: true` ở main áp dụng mặc định cho toàn JAR | Dùng per-package section hoặc `Sealed: false` để override |
| Hai loader cùng nạp package sealed mà không lỗi | Hai namespace package/runtime riêng | Đây có thể là hành vi hợp lệ; kiểm tra identity |
| Cùng package unsealed nhưng cast vẫn lỗi | Trùng FQCN ở defining loader khác nhau | Chia sẻ API type qua parent loader |
| Đổi tên JAR nhưng sealing vẫn lỗi | Hai code source URL khác nhau/đường tìm vẫn tách bytecode | Gộp package vào một JAR hoặc sửa dependency topology |
| File class có mặt nhưng loader từ chối định nghĩa | Sealing, signer consistency hoặc lỗi bytecode | Xem đầy đủ cause và nguồn class đã chọn |
| Metadata không phản ánh version mọi class | Package được định nghĩa một lần, không theo mỗi class | Kiểm tra CodeSource của class riêng |

## 12. Checklist để thiết kế JAR không lỗi sealing

1. **Biết những package nào xuất hiện trong các dependency JAR.** Kiểm tra entry `demo/locked/*.class` bằng `jar --list --file ...`.
2. **Đọc manifest thật trong JAR runtime.** Xác minh main/per-entry `Sealed`, tên package path, dòng trống và cấu trúc manifest.
3. **Không rải một sealed package qua nhiều JAR trong cùng defining loader.** Nếu cần split, cân nhắc tổ chức lại module/package hoặc bỏ sealing có chủ đích sau khi xem tác động.
4. **Không nhầm parent loader với superclass của ClassLoader.** Sealing kiểm soát package class được một loader định nghĩa từ code source; parent delegation có thể đưa class từ loader khác.
5. **Nhất quán build và runtime classpath.** Maven/Gradle shading, fat JAR hoặc relocation có thể thay đổi package layout và manifest; kiểm tra artifact cuối sau build.
6. **Không copy `Sealed: true` từ JAR khác vô thức.** Nếu đóng nhiều thư viện vào một JAR, cần thiết kế metadata và nguồn code phù hợp.
7. **Xử lý package metadata/version theo đúng nghĩa.** Không xem `Implementation-Version` là contract kiểm soát tương thích.
8. **Có test cả thứ tự load thuận/ngược khi split package.** Lỗi sealing có thể xuất hiện ở bước nạp class thứ hai, không nhất thiết ngay khi tạo loader.
9. **Phân biệt classpath và module path.** Với JPMS, kiểm tra module resolution và package encapsulation riêng.
10. **Giữ quyền truy cập file và nguồn code đáng tin cậy.** Sealing không thay thế xác minh integrity hoặc sandbox.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `a.jar` khai báo `Name: demo/locked/`, `Sealed: true`. `b.jar` chứa class khác trong `demo.locked`. Một `URLClassLoader` đã nạp Anchor từ A, rồi nạp Other từ B. Kết quả?

**Đáp án:** Vi phạm sealing, thường `SecurityException`, vì package đã sealed tại code source A.

**Câu 2.** Nếu class B được nạp trước khi class A, lỗi sealing có chắc biến mất không?

**Đáp án:** Không. B có thể tạo `demo.locked` dạng unsealed, sau đó A muốn sealed cùng package trong loader nên cũng gây sealing violation.

**Câu 3.** `Sealed: true` ở main section khác gì ở `Name: demo/locked/`?

**Đáp án:** Main section đặt default cho tất cả package của JAR. Named section đặt/ghi đè giá trị cho package cụ thể.

**Câu 4.** Hai ClassLoader độc lập nạp hai class cùng `demo.locked` từ hai JAR khác nhau có nhất thiết vi phạm sealing không?

**Đáp án:** Không. Mỗi loader có namespace package riêng; việc sealing được kiểm tra trong lúc một loader định nghĩa class thuộc package của chính nó.

**Câu 5.** `Package.getImplementationVersion()` có tự ngăn ứng dụng chạy sai phiên bản dependency không?

**Đáp án:** Không. Đây là metadata, không phải dependency solver; ứng dụng/build tool phải tự kiểm tra compatibility.

**Câu 6.** Package sealed có đồng nghĩa JAR đã được ký số và đáng tin cậy không?

**Đáp án:** Không. Sealing nhằm nhất quán nguồn class trong package; signing và kiểm soát quyền chạy là các vấn đề khác.

**Câu 7.** Nếu hai JAR chứa **cùng binary class name** nhưng loader chỉ nạp class từ JAR A, có tự động sealing violation không?

**Đáp án:** Không. Lỗi sealing liên quan đến cố định nghĩa nhiều class thuộc cùng package từ những code source không tương thích; chỉ có file trùng tên nằm trên disk chưa đồng nghĩa loader đã định nghĩa cả hai.

## 14. Tài liệu chính thức

- [Java SE 17 — JAR File Specification, Package Sealing](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): ngữ nghĩa `Sealed` ở main/per-package section và code source.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL search, `definePackage(Manifest, URL)`, package metadata.
- [Java SE 17 — Package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html): `isSealed`, `isSealed(URL)`, specification/implementation metadata và compatibility.
- [Java SE 17 — JarFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html): đọc JAR và manifest.
- [Java SE 17 — Manifest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/Manifest.html): main attributes và named entries.
- [Java Virtual Machine Specification 17 — Loading and Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime class identity và quy trình class loading.

**Ghi nhớ:** `Sealed: true` trong manifest ràng buộc class của **một package** phải xuất phát từ **một code source JAR nhất quán trong cùng defining loader**. Manifest có thể đặt default toàn JAR hoặc override ở từng package. Metadata `Specification-*`/`Implementation-*` hỗ trợ mô tả version, nhưng không tự đảm bảo compatibility hay bảo mật.