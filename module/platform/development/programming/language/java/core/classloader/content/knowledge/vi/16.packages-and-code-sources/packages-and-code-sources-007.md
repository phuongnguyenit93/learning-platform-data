# Chữ ký JAR, chứng thư và tính nhất quán trong cùng package

## 1. Vấn đề: cùng package nhưng có thể không được nạp chung

Khi một class loader lấy các class từ nhiều JAR, JVM và class loader không chỉ quan tâm **tên class** và **bytecode**. Với JAR được ký, còn có thông tin **chữ ký số (digital signature)** và **chứng thư (certificate)** gắn với các entry đã được xác minh. Với JAR có package sealing, còn có ràng buộc **các class trong cùng package phải đến từ một nguồn JAR nhất quán** theo cơ chế sealing.

Ví dụ:

~~~text
plugin-a.jar (đã ký bằng signer A)
  com/example/shared/Alpha.class

plugin-b.jar (không ký)
  com/example/shared/Beta.class

                 URLClassLoader L
                      |
             define com.example.shared.Alpha
                      |
          package certificate set = {A}
                      |
             define com.example.shared.Beta
                      |
            certificate set = {} -> không khớp
                      |
                SecurityException
~~~

Đây là **kịch bản nguyên tắc**: hai class đều do **cùng một defining loader L** cố định nghĩa trong **cùng package**, nhưng certificate sets không giống nhau. Theo Javadoc Java 17 của `ClassLoader.defineClass`, **class đầu tiên được định nghĩa trong một package xác lập tập certificates chính xác**; các class được thêm vào package đó trong cùng loader phải có **cùng tập** hoặc có thể gặp `SecurityException`.

Một cơ chế khác là **package sealing**: khi package được khai báo `Sealed: true` trong manifest JAR, loader xử lý manifest/sealing sẽ không cho lấy thêm class của package đã sealed từ một code source JAR khác. Vi phạm có thể gây `SecurityException`, ngay cả khi hai JAR được ký bằng cùng certificate set.

**Đừng đồng nhất ba việc:**

1. **Xác minh chữ ký JAR (integrity verification):** bytes của các entry được ký có còn nhất quán với thông tin chữ ký?
2. **Quyết định tin cậy signer (trust validation):** signer/certificate có được tổ chức tin tưởng theo trust policy, chain, thời hạn, key usage và các điều kiện phù hợp không?
3. **Tính nhất quán package trong một loader:** certificates của các class cùng package có trùng nhau không, package sealing có bị vi phạm không?

Cả ba có quan hệ nhưng là **những phép kiểm tra khác nhau**. Chữ ký hợp lệ về mặt mật mã không tự làm JAR trở thành “an toàn để thực thi”, và không tự biến certificate self-signed thành một identity đáng tin.

## 2. Bốn khái niệm nền tảng

### 2.1. Binary class name và runtime package

Với class:

~~~java
package com.example.shared;

public final class Alpha {}
~~~

`com.example.shared.Alpha` là binary name; `com.example.shared` là package name. Ở runtime, JVM còn xét defining loader để xác định **runtime package**. Hai class trùng package name nhưng được định nghĩa bởi hai loader khác nhau **không tự thuộc một runtime package duy nhất**.

Điều này ảnh hưởng tới package-private access, type identity và khi phân tích package consistency. Quy tắc certificate set khi `ClassLoader.defineClass` được áp dụng trong **phạm vi loader/package mà loader định nghĩa**; nó không phải một bảng certificate toàn JVM chung cho mọi loader.

### 2.2. Chữ ký JAR và certificate

Một JAR được ký theo cơ chế chuẩn JAR signing có thể chứa dữ liệu liên quan trong `META-INF/`, chẳng hạn manifest `MANIFEST.MF`, signature file `.SF` và signature block `.RSA`, `.DSA` hoặc `.EC` tùy thuật toán và công cụ.

`jarsigner` sử dụng private key để ký; signature verification kiểm tra các bytes/manifest digests theo cơ chế JAR. Certificate gắn với signer giúp người xác minh đánh giá identity/public key của bên ký theo chính sách riêng.

Không đánh đồng:

- **Digest:** dùng để phát hiện thay đổi nội dung được bảo vệ.
- **Digital signature:** dùng private key ký dữ liệu liên quan; verification sử dụng public key.
- **Certificate:** liên kết public key với thông tin định danh, có thể nằm trong certificate chain.
- **Trust:** kết luận một chain/signer được chấp nhận dựa vào trust store, nguồn CA, thời hạn, revocation, thuật toán, timestamp và policy của ứng dụng.

Một JAR có signature hợp lệ vẫn có thể là mã độc nếu signer không đáng tin hoặc mã hợp lệ nhưng nguy hiểm. Một package consistency check chỉ so **certificate sets**, không thay thế quá trình xác minh chính sách trust.

### 2.3. CodeSource

`java.security.CodeSource` đại diện cho **vị trí nguồn code** (thường là URL) và thông tin certificates hoặc code signers liên quan. Nó có thể được liên kết với `ProtectionDomain` khi class được định nghĩa.

Ví dụ minh họa về quan sát:

~~~java
java.security.ProtectionDomain pd = SomeClass.class.getProtectionDomain();
java.security.CodeSource source =
        pd == null ? null : pd.getCodeSource();
System.out.println(source == null ? null : source.getLocation());
~~~

Đây là **đoạn trong một phương thức**, với `SomeClass` là class có thật. Location URL dùng để hỗ trợ quan sát xuất xứ, nhưng **không đủ** để chứng minh signature hợp lệ hoặc publisher được tin cậy. Có runtime/protection domain mà `CodeSource` không cung cấp thông tin đầy đủ.

### 2.4. Package sealing

**Sealing** là thuộc tính của **package**, thường được đọc từ JAR manifest khi loader hỗ trợ cơ chế này. Nếu package được sealed, các class của package đó phải có nguồn phù hợp với **seal base URL**, thường là cùng JAR. Đây là ràng buộc nguồn, không phải ràng buộc về sự bằng nhau của certificate sets.

Có thể dùng `Package.isSealed()` và `Package.isSealed(URL)` để kiểm tra thông tin package mà loader đã định nghĩa, nhưng cần nhớ object `Package` và sealing có phạm vi theo loader và cơ chế define package cụ thể.

## 3. ClassLoader.defineClass yêu cầu certificate set nhất quán

Trong Java SE 17, overload quan trọng là:

~~~java
protected final Class<?> defineClass(
        String name,
        byte[] bytes,
        int offset,
        int length,
        java.security.ProtectionDomain domain)
~~~

`name` phải là **binary name** của class file; nếu không trùng với internal name của bytes, JVM có thể ném `NoClassDefFoundError`. Với `name` không null, Javadoc nêu quy tắc:

- **Class đầu tiên** được định nghĩa trong một package xác định **tập certificates** mà các class tiếp theo trong package ấy phải sử dụng.
- Certificates được lấy từ `CodeSource` nằm trong `ProtectionDomain` của class.
- Nếu một class khác của cùng package trong loader ấy có certificate set khác, quá trình define có thể ném **`SecurityException`**.
- Certificate set có thể là **tập rỗng** (unsigned), và unsigned so với signed là không nhất quán.
- Tên bắt đầu `java.` có giới hạn đặc biệt về loader được phép định nghĩa; quy tắc này **độc lập** với chữ ký JAR.
- Khi tự gọi `defineClass`, nên cung cấp **binary name không null** để những kiểm tra liên quan được thực hiện đầy đủ.

Sơ đồ:

~~~text
Defining Loader L
   |
   +-- class p.First    CodeSource certificates = [cert A]
   |                    -> ghi nhận signer set cho p
   |
   +-- class p.Second   CodeSource certificates = [cert A]
   |                    -> nhất quán
   |
   +-- class p.Third    CodeSource certificates = []
                        -> SecurityException
~~~

**Trật tự nạp có thể làm tên class “bị từ chối” khác nhau**: bản đầu tiên định nghĩa trong package xác lập certificate set; class tiếp theo không phù hợp mới bị từ chối. Điều đó không có nghĩa class được nạp đầu tiên luôn được tin cậy: ràng buộc chỉ giữ **tính đồng nhất** trong cùng loader.

`defineClass(String, byte[], int, int)` (không có `ProtectionDomain` tường minh) sử dụng default protection domain. Đừng dùng overload đó khi đang có **verified signer metadata** của các JAR khác nhau rồi mong JVM tự biết signer của từng entry chỉ từ mảng bytes.

## 4. Package sealing: cùng signer vẫn có thể bị từ chối

Manifest có thể khai báo sealed cho toàn JAR:

~~~text
Manifest-Version: 1.0
Sealed: true
~~~

Hoặc chỉ cho một package cụ thể:

~~~text
Manifest-Version: 1.0

Name: com/example/shared/
Sealed: true
~~~

Lưu ý manifest có định dạng và quy tắc **dòng trống** rõ ràng: main section đứng trước, package section bắt đầu bằng `Name: .../`, tên path sử dụng `/`. Việc chỉnh manifest thủ công cần tôn trọng encoding/line-folding của chuẩn JAR.

Nếu một `URLClassLoader` nạp `com.example.shared.Alpha` từ `sealed-a.jar` và define package với seal base URL của `sealed-a.jar`, việc sau đó cố nạp `com.example.shared.Beta` trong **cùng loader/package** từ `other.jar` có thể gây **sealing violation**.

Điểm phân biệt:

| Tình huống | Certificate consistency | Package sealing |
| --- | --- | --- |
| Cùng signer certificates, khác JAR, package không sealed | Có thể hợp lệ về chứng thư | Không bị chặn bởi sealing |
| Khác signer/unsigned, cùng package và loader | Có thể `SecurityException` | Có thể không sealed |
| Cùng signer, hai JAR, package sealed ở JAR đầu | Certificate sets có thể khớp | Có thể `SecurityException` vì khác seal base |
| Hai loaders riêng, mỗi loader tự định nghĩa package | Mỗi loader kiểm tra tập riêng | Mỗi loader quản lý package/seal của mình |
| Một JAR được ký nhưng chứa unsigned entry cùng package | Có thể mismatch khi define | Sealing là kiểm tra tách biệt |

**Sealing không tự thực hiện xác minh trust**, và **signer equality không thay thế sealing**. Không nên xử lý lỗi sealing bằng cách bỏ metadata chữ ký hoặc sửa manifest của thư viện bên thứ ba tùy tiện.

## 5. Ví dụ Java 17+: ký một JAR, nạp chung với JAR unsigned

Ví dụ sau chạy trên **JDK 17+** với công cụ `javac`, `jar`, `keytool` và `jarsigner`. Nó minh họa **certificate consistency** thật khi một `URLClassLoader` thử định nghĩa hai class **cùng package** từ hai JAR có trạng thái ký khác nhau.

Đây là ví dụ học tập dùng **keystore và mật khẩu minh họa công khai**, **không sử dụng key này trong hệ thống thực**. Chứng thư self-signed chỉ để tạo chữ ký thử nghiệm; nó không đại diện một certificate chain được tổ chức tin cậy.

### 5.1. Cấu trúc source

Tạo dự án:

~~~text
jar-signing-lab/
├── src/
│   ├── pack/
│   │   ├── A.java
│   │   └── B.java
│   └── SignatureBoundaryDemo.java
└── (các thư mục output sẽ tạo ở các bước sau)
~~~

File **src/pack/A.java**:

~~~java
package pack;

public final class A {
    public String name() {
        return "A";
    }
}
~~~

File **src/pack/B.java**:

~~~java
package pack;

public final class B {
    public String name() {
        return "B";
    }
}
~~~

Hai class nằm trong cùng Java package `pack` nhưng được đóng trong **hai JAR khác nhau**. Chúng không phụ thuộc vào nhau.

### 5.2. File host: src/SignatureBoundaryDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class SignatureBoundaryDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: SignatureBoundaryDemo <signed.jar> <unsigned.jar>");
        }

        URL signed = Path.of(args[0]).toAbsolutePath().toUri().toURL();
        URL unsigned = Path.of(args[1]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { signed, unsigned },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> a = Class.forName("pack.A", false, loader);
            Object[] signers = a.getSigners();
            System.out.println("A loaded: " + (a != null));
            System.out.println("A signed: "
                    + (signers != null && signers.length > 0));

            try {
                Class.forName("pack.B", false, loader);
                System.out.println("B loaded: true");
            } catch (SecurityException mismatch) {
                System.out.println("B rejected: SecurityException");
            }
        }
    }
}
~~~

Vì host được chạy chỉ với `host-out` trên classpath và loader có parent là **platform loader**, bản `pack.A` và `pack.B` được tải từ hai URL theo phạm vi của `URLClassLoader` trong bài. `Class.forName(name, false, loader)` yêu cầu load/link theo API mà không chủ động chạy static initializers.

Hãy đọc ý nghĩa `a.getSigners()` đúng phạm vi: nó quan sát thông tin signers gắn với **Class đã được định nghĩa**; nó không thay thế việc đánh giá policy tin cậy của CA/chứng thư. Chương trình cố ý chỉ in boolean, không in chuỗi chứng thư khác nhau theo environment.

### 5.3. Tạo các thư mục output

Trên Linux/macOS với shell tương thích:

~~~bash
mkdir -p signed-out unsigned-out host-out
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force signed-out, unsigned-out, host-out | Out-Null
~~~

Các lệnh còn lại sử dụng tool CLI của JDK và có thể chạy dưới terminal phù hợp sau khi đứng tại thư mục `jar-signing-lab`.

### 5.4. Compile và tạo hai JAR

~~~bash
javac --release 17 -d signed-out src/pack/A.java
javac --release 17 -d unsigned-out src/pack/B.java
javac --release 17 -d host-out src/SignatureBoundaryDemo.java

jar --create --file a-signed.jar -C signed-out .
jar --create --file b-unsigned.jar -C unsigned-out .
~~~

Tên `a-signed.jar` ở giai đoạn này **chỉ là tên file**; nó **chưa có chữ ký**. Chúng ta ký nó ở bước kế tiếp. `b-unsigned.jar` được giữ unsigned.

### 5.5. Tạo test key/certificate

Chạy lệnh **một dòng** sau để hạn chế khác biệt cú pháp nối dòng giữa shell:

~~~bash
keytool -genkeypair -alias demo -keyalg RSA -keysize 2048 -validity 365 -dname "CN=Training, OU=Demo, O=Example, L=Hanoi, ST=Hanoi, C=VN" -keystore training.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
~~~

Keytool tạo key pair và certificate self-signed cho mục đích thử nghiệm. Password `changeit` xuất hiện ngay trong ví dụ **không phải cách quản lý secret cho production**. Đừng commit keystore/private key của hệ thống thật vào repository hay command history có khả năng bị chia sẻ.

### 5.6. Ký JAR A

~~~bash
jarsigner -keystore training.p12 -storetype PKCS12 -storepass changeit -keypass changeit a-signed.jar demo
~~~

Công cụ có thể in cảnh báo rằng certificate được self-signed, không có timestamp hoặc không được trust; đó là **giới hạn cố ý của demo**, không phải kỳ vọng mọi chính sách security đều chấp nhận signer này.

Để xem verification từ công cụ:

~~~bash
jarsigner -verify -verbose -certs a-signed.jar
~~~

Output `jarsigner` có thể gồm thông tin thuật toán, tên signer, warnings, timestamp và trạng thái khác nhau tùy JDK. **Không sử dụng stdout của lệnh này làm snapshot cố định**. Chế độ `-strict` có thể trả nonzero vì cảnh báo certificate của bài thử self-signed, dù dữ liệu JAR không bị chỉnh sửa.

Quan trọng hơn: `jarsigner -verify` kiểm tra chữ ký theo thuật toán/quy tắc công cụ, **không có nghĩa tổ chức của bạn đã trust certificate hay audit code trong JAR**.

### 5.7. Chạy host demo

~~~bash
java -cp host-out SignatureBoundaryDemo a-signed.jar b-unsigned.jar
~~~

Với JDK 17+ tiêu chuẩn, hai JAR được tạo đúng và signer metadata được xác minh, **stdout chính xác của chương trình** là:

~~~text
A loaded: true
A signed: true
B rejected: SecurityException
~~~

Giải thích:

1. `pack.A` đến từ `a-signed.jar`, có code signers được liên kết với class sau khi JAR entry được xác minh.
2. `URLClassLoader` define `pack.A` trong package `pack` với tập certificate của signer thử nghiệm.
3. Khi loader này cố define `pack.B` từ `b-unsigned.jar`, cùng package `pack` nhưng certificate set rỗng, không còn khớp với tập đã xác lập.
4. `ClassLoader.defineClass` phát hiện package certificate mismatch, ném `SecurityException`; demo bắt đúng loại lỗi để in dòng cuối.
5. Java source `B` hợp lệ, JAR `b-unsigned.jar` cũng có thể mở/read bình thường. Vấn đề là **không thể bổ sung Class B có certificate khác vào cùng package trong cùng defining loader**.

**Đây không phải demonstration package sealing.** Hai JAR tạo bằng `jar --create` trong ví dụ không cố ý khai báo `Sealed: true`; lỗi do sự khác biệt certificates, không phải seal base.

### 5.8. Biến thể: tách class loaders

Nếu `pack.A` được định nghĩa bởi loader L1, còn `pack.B` bởi loader L2 độc lập, certificate consistency được kiểm tra riêng theo phạm vi mỗi loader. Chỉ xét quy tắc certificate cùng package, L1 và L2 **không cần có signer sets bằng nhau**, vì mỗi loader có package definitions riêng.

Nhưng điều đó **không biến hai loader thành môi trường có thể trao đổi mọi class tùy ý**: package-private access và runtime type identity khác nhau, và host/plugin có thể gặp lỗi kiểu khi dùng chung API. Không sửa một lỗi certificate mismatch bằng cách tách loader nếu kiến trúc thực sự cần hai class có cùng runtime package để truy cập package-private members.

## 6. Vì sao signed JAR có thể có entry unsigned?

Ký JAR không phải lúc nào cũng đồng nghĩa **mọi entry đang có trong archive** đều được ký. Người ta có thể thêm entry mới sau khi ký, hoặc một manifest/signature chỉ bảo vệ những entries cụ thể; khi đó có thể tồn tại hỗn hợp signed và unsigned entries.

Khi `JarFile` được mở ở chế độ verification và entry bytes đã được đọc/kiểm tra, `JarEntry.getCodeSigners()` hoặc `getCertificates()` cung cấp thông tin liên quan **entry đó** nếu có. Nếu entry không được ký, giá trị có thể là null. Nếu lấy metadata trước khi đọc xong verified entry, chưa thể kết luận một cách chắc chắn chỉ từ `null` đó.

Đối với **multi-release JAR**, entry dành cho Java version cụ thể có thể có chữ ký riêng; `JarFile` Javadoc Java 17 nói tới việc xác minh nội dung versioned entry với chính signature của entry ấy.

Hệ quả đối với class loading:

- Kiểm tra **từng class entry** khi xác định signer/certificate consistency, thay vì gắn nhãn “JAR ký” cho tất cả entries.
- Nếu package đã có class mang signer set A, một class unsigned cùng package trong cùng loader có thể gây mismatch.
- Build/repackaging fat JAR có thể thay đổi danh sách entries và metadata chữ ký; không được sao chép thư mục `META-INF` signature cũ sang bytes mới rồi giả định chữ ký vẫn hợp lệ.
- **Đừng tự động xóa `.SF`/`.RSA`** để “sửa” verification hoặc package certificate error. Việc đó làm mất bằng chứng nguồn gốc và có thể vi phạm chính sách deployment.

## 7. Dùng JarFile để xem chữ ký entry: đọc hết trước khi kiểm tra

Ví dụ Java 17+ có thể được dùng như một utility phụ cho demo, nhưng không dùng nó để kết luận signer được tin cậy theo chính sách doanh nghiệp.

Tạo file **InspectEntry.java**:

~~~java
import java.io.InputStream;
import java.nio.file.Path;
import java.security.CodeSigner;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class InspectEntry {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: InspectEntry <jar-file> <entry-name>");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile(), true)) {
            JarEntry entry = jar.getJarEntry(args[1]);
            if (entry == null) {
                throw new IllegalArgumentException(
                        "Entry missing: " + args[1]);
            }

            try (InputStream in = jar.getInputStream(entry)) {
                in.transferTo(java.io.OutputStream.nullOutputStream());
            }

            CodeSigner[] signers = entry.getCodeSigners();
            System.out.println("signed entry: "
                    + (signers != null && signers.length > 0));
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 InspectEntry.java
~~~

Sau khi đã tạo/ký hai JAR trong mục 5:

~~~bash
java InspectEntry a-signed.jar pack/A.class
java InspectEntry b-unsigned.jar pack/B.class
~~~

**Stdout của từng lần gọi** theo đúng thứ tự trên:

~~~text
signed entry: true
~~~

~~~text
signed entry: false
~~~

Lưu ý:

- Constructor `JarFile(file, true)` bật verification; quá trình đọc hết entry stream mới cung cấp đầy đủ điều kiện kiểm tra digest/signature cho entry đã ký.
- `getCodeSigners()` là metadata của JAR entry sau verification, **không tự xác nhận trusted CA**.
- Nếu JAR bị sửa khiến signature validation fail, có thể phát sinh `SecurityException` khi đọc entry; helper không nuốt lỗi và không in một kết quả “false” đánh lừa.
- Với multi-release JAR cần xác định đúng entry version đang được xem; không khái quát mọi versioned class từ một entry ở root.

## 8. CodeSource, ProtectionDomain và custom ClassLoader

Một custom loader có thể gọi overload:

~~~java
Class<?> type = defineClass(
        binaryName, classBytes, 0, classBytes.length,
        protectionDomain);
~~~

**Đây là đoạn minh họa trong subclass `ClassLoader`**, chưa có khai báo các biến hay mã chạy độc lập.

Tại đây:

- `binaryName` cần phản ánh tên thật trong classfile; không nên truyền `null` để né các kiểm tra tên/certificate.
- `classBytes` cần đến từ nguồn đã được phê duyệt; việc có bytes không chứng minh source đáng tin.
- `protectionDomain` có thể có `CodeSource`, trong đó chứa URL và signer/certificate information.
- Nếu đã có verification đúng của signed JAR, cần **bảo toàn signer metadata của từng entry** khi định nghĩa Class; không tự tuyên bố bytecode unsigned là signed.
- Nếu tự dùng overload `defineClass(name, bytes, off, len)` không có `ProtectionDomain` thích hợp, bạn có thể làm mất dấu vết CodeSource/signers như những loader chuyên dùng JAR vẫn duy trì.

Một số ứng dụng custom loader từ filesystem hoặc storage riêng cần định nghĩa rõ source provenance, signer verification, package sealing, classpath sharing và cách xử lý errors. **Không nên làm một “security shim” bằng cách tự tạo `CodeSource` với certificate tự gán mà chưa hề xác minh bytes.**

`ProtectionDomain` và Java `SecurityManager` là những thành phần lịch sử của mô hình Java security. Ở JDK 17, Security Manager đã được đánh dấu deprecated for removal; những permission models cũ không nên được coi là một sandbox hiện đại mặc định cho mã không tin cậy. Tuy nhiên **package certificate consistency** trong `defineClass` vẫn là ràng buộc JVM/JDK liên quan tới hành vi class loading và signer sets.

## 9. Certificate equality không giống trust validation

Đặt hai câu hỏi riêng:

**Câu hỏi A: “Các class của package này có cùng signer certificate set không?”**

Đây là vấn đề Javadoc của `ClassLoader.defineClass`. Nếu `pack.A` có set A và `pack.B` có set B, so sánh **bộ certificates tương ứng**, không phải chỉ so text alias tên `demo`, đường dẫn JAR hoặc organization name.

**Câu hỏi B: “Signer này có được tin cậy để chạy code không?”**

Đây là trust/policy decision: certificate chain có được xác thực đến trust anchor được chấp nhận, thuật toán có đủ mạnh, chữ ký và timestamp có hợp lệ, certificates có đúng phạm vi mục đích, tổ chức có approve publisher/artifact/hash hay không.

Hai JAR cùng certificate set **có thể** thỏa package signer consistency mà vẫn là code không được phép chạy theo policy doanh nghiệp. Ngược lại, hai JAR từ **hai CA có uy tín khác nhau** vẫn có thể không có **cùng exact signer set**, nên không thể trộn cùng package trong một loader.

Không nhầm thứ tự certificate chain hiển thị với quy tắc equality của Java API; không viết chính sách business dựa vào string repr của `Certificate.toString()`. Nếu cần pinning, dùng các API mã hóa, fingerprint và trust stores do thư viện security phù hợp cung cấp.

## 10. Sealing và package-info trong môi trường nhiều JAR

`ClassLoader.definePackage` cho phép xác định metadata như specification/implementation title, version, vendor và seal base. Khi loader đọc JAR manifest, một số loader như `URLClassLoader` dùng dữ liệu đó để thiết lập package properties.

Cùng package có thể xuất hiện trong nhiều JAR, nhưng kết quả tùy theo:

- **Package sealing:** có sealed không, seal base là URL nào, package đã được define hay chưa.
- **Package certificate consistency:** mỗi Class được define bởi loader có certificate set nào.
- **Thứ tự class được nạp:** class đầu tiên có thể quyết định certificate set và metadata/seal của package.
- **Package identity:** các classes có cùng defining loader không, hay đang ở loader khác nhau?
- **Named modules:** package/module rules của JPMS có thể bổ sung ràng buộc; không giả định classpath/JAR sealing vận hành y hệt với mọi custom named module layer.

Javadoc Java 17 của `ClassLoader.definePackage` lưu ý rằng loader mong metadata chính xác từ JAR nên gọi `definePackage` **trước `defineClass`**, nếu cần truyền manifest/seal info. Nếu `defineClass` tự tạo Package trước với metadata mặc định, cố định nghĩa lại package properties sau đó không phải cách thiết kế đáng tin cậy.

Đừng dùng `getPackage(String)` (đã deprecated từ Java 9) để kết luận package do chính loader hiện tại define: API cũ có thể tìm package từ ancestors. `getDefinedPackage(String)` rõ hơn khi muốn xem package do **chính loader đó** định nghĩa.

## 11. Gợi ý tạo JAR sealing riêng để nghiên cứu

Để nghiên cứu sealing **tách biệt** khỏi chữ ký, có thể tạo hai JAR **unsigned** với cùng package `pack`:

~~~text
a-sealed.jar   : chứa pack/A.class và manifest Sealed: true
b-unsigned.jar : chứa pack/B.class
~~~

Manifest mẫu trong file `sealed.mf`:

~~~text
Manifest-Version: 1.0
Sealed: true
~~~

Sau khi đã compile `pack.A` và `pack.B`:

~~~bash
jar --create --file a-sealed.jar --manifest sealed.mf -C signed-out .
~~~

`jar` có thể bổ sung/chỉnh các metadata manifest phù hợp. Khi một `URLClassLoader` nạp A từ `a-sealed.jar` trước, nó định nghĩa package `pack` là sealed đối với code source của JAR đó. Nếu sau đó cùng loader nạp B từ `b-unsigned.jar`, class B có thể bị từ chối vì **sealing violation**, dù cả hai class đều unsigned và certificate sets bằng nhau.

Đây là **bài tập quan sát dựa trên ví dụ `SignatureBoundaryDemo`**, cần đổi đối số sang `a-sealed.jar b-unsigned.jar` rồi xác định loại lỗi/stack trace của runtime. Lúc đó dòng `A signed: ...` có thể là false, còn dòng cuối báo `SecurityException`; nguyên nhân là package sealing, không phải mismatch certificate.

**Không đặt `Sealed: true` vào ví dụ signer ở mục 5**, vì như vậy hai kiểm tra cùng lúc có thể che nguyên nhân cần học.

## 12. Khi nào cùng tên package vẫn load được từ hai JAR?

Trong cơ chế classpath truyền thống, một loader như `URLClassLoader` thường có thể nạp class `p.A` từ JAR 1 và `p.B` từ JAR 2 nếu:

1. Các JAR đều nhìn thấy qua search URLs.
2. Package không bị sealing policy ngăn nguồn thứ hai.
3. Certificate sets của class entries tương thích theo `defineClass`.
4. Class name/bytecode hợp lệ và không xung đột định nghĩa trùng cùng binary name trong loader.
5. Các dependency và loader constraints liên quan có thể được giải quyết.

Ví dụ cả hai JAR **unsigned**, package unsealed, thường có thể nạp chung. Nhưng điều này vẫn có rủi ro về split package/versioning và build reproducibility. Đừng xem “nạp được” là bằng chứng mọi API hoặc security policy đều đúng.

Nếu **khác defining loaders**, việc trộn cùng package name ở source không đồng nghĩa chúng ở cùng runtime package: package-private access và type identity có thể không tương thích. “Dùng loader khác để hết SecurityException” có thể thay một lỗi bằng nhiều lỗi class isolation khác.

Trong JPMS, **named modules** có những kiểm tra package/module ownership và readability khác. Split packages giữa named modules có thể bị module resolution từ chối dù classpath tương tự trước đây từng chạy được. Không dùng kết luận “unsigned/unsealed => luôn chạy được” cho JPMS.

## 13. Lỗi thường gặp khi làm fat JAR, shading, repackaging

### 13.1. Trộn classes signed và unsigned vào cùng package

Một fat JAR builder có thể trộn nhiều JAR phụ thuộc, trong đó có signed JAR, thành một JAR mới. Nếu giữ các signature metadata `META-INF` nguyên vẹn nhưng thay nội dung/manifest, quá trình verification có thể thất bại. Nếu xóa chữ ký mà không kiểm soát provenance/trust policy, artifact mất thông tin signer; đó không phải “sửa” integrity.

**Hướng đúng:** build pipeline phải có chính sách rõ về signed input JARs, stripping/re-signing trong hoàn cảnh được phép, artifact attestation và kiểm tra kết quả. Nếu thay bytes, chữ ký gốc không còn xác nhận đúng sản phẩm mới.

### 13.2. Hai versions của cùng thư viện cùng package

Nếu một class `com.example.Util` tồn tại trong hai JAR, parent-first/wildcard classpath order có thể khiến loader lấy version không mong muốn. Sealing và signer checks có thể phát hiện một số tình huống trộn, nhưng không phải hệ thống giải quyết dependency version.

### 13.3. Package split trên classpath

Hai JAR cùng đặt class vào `com.example.shared` là split package theo nghĩa đóng gói nguồn. Classpath truyền thống có thể xử lý được nếu signer/sealing nhất quán, nhưng vẫn dễ bị xung đột. Named modules có ràng buộc mạnh hơn.

### 13.4. Annotation hoặc API bị nhân đôi qua loaders

Ngay cả nếu mỗi loader không vi phạm certificate set/sealing của chính nó, host và plugin có thể định nghĩa hai bản `shared.Api` cùng tên. Điều này gây lỗi kiểu runtime và annotation mismatch. **Signer/sealing checks không làm hai Class từ hai defining loaders trở thành cùng kiểu**.

## 14. Chẩn đoán SecurityException đúng cách

Một `SecurityException` khi load class có thể liên quan package certificate mismatch, sealing violation, hạn chế định nghĩa package `java.*` hoặc quy định runtime khác.

Đừng đoán chỉ từ chữ “security” trong exception. Thu thập:

1. **Stack trace và message** đầy đủ, xác định lỗi ở `URLClassLoader`, `ClassLoader.defineClass`, manifest/seal hay JAR verification.
2. **Binary name** đang load và package name, ví dụ `pack.B` / `pack`.
3. **Defining loader identity**, có phải cùng loader đã định nghĩa class package trước đó không?
4. **Code source/JAR URL** của class đã load thành công, signer certificates nếu được cung cấp.
5. **Manifest**: có `Sealed: true` ở main hoặc per-package section không?
6. **JAR signature metadata**: `jarsigner -verify -verbose -certs` cho mỗi input artifact; có warnings unsigned entries hay self-signed certificate không?
7. **Classpath/URL order**: JAR nào cung cấp class đầu tiên; có JAR/version trùng không?
8. **Build/repackage step**: có merge/shade/re-sign làm thay đổi bytes hay signature metadata không?
9. **Runtime JPMS/module layer**: package này có thuộc named module không, có split package?
10. **Trust policy**: signer có được tổ chức tin cậy không, tách riêng khỏi kiểm tra signer equality.

Mẫu quan sát `CodeSource` của class đã nạp:

~~~java
static void inspect(Class<?> clazz) {
    java.security.ProtectionDomain pd = clazz.getProtectionDomain();
    java.security.CodeSource cs = pd == null ? null : pd.getCodeSource();
    System.out.println("class: " + clazz.getName());
    System.out.println("loader: " + clazz.getClassLoader());
    System.out.println("source: " +
            (cs == null ? "unknown" : cs.getLocation()));
    Object[] signers = clazz.getSigners();
    System.out.println("has signers: " +
            (signers != null && signers.length > 0));
}
~~~

Đây là **đoạn minh họa đặt trong class khác**, không phải một chương trình có `main`. Với `CodeSource` null hoặc `getSigners()` null, cần diễn giải theo loader/cơ chế định nghĩa class thay vì tự kết luận “artifact không đáng tin”.

## 15. Công cụ kiểm tra phù hợp

| Công cụ/API | Dùng để làm gì | Không thay thế điều gì |
| --- | --- | --- |
| `jar --list --file x.jar` | Liệt kê entries, tìm class/manifest/signature files | Xác minh trust signer |
| `jar --describe-module --file x.jar` | Xem descriptor/module info liên quan | Certificate consistency |
| `jarsigner -verify -verbose -certs x.jar` | Kiểm tra signature và thông tin signer/warnings | Xác nhận code vô hại |
| `keytool -list -v -keystore store.p12` | Quan sát certificate/alias trong keystore | Kiểm tra mọi JAR entry |
| `JarFile(file, true)` + đọc hết entry | Kích hoạt signature verification cho signed entry được đọc | Trust policy của CA tổ chức |
| `JarEntry.getCodeSigners()` | Quan sát signer sau verification | Chứng minh artifact an toàn |
| `Class.getSigners()` | Quan sát signers của runtime Class | Hoàn chỉnh chain/trust validation |
| `Package.isSealed()` | Kiểm tra package metadata sealing | Xác minh certificate/trust |
| `Class.getProtectionDomain().getCodeSource()` | Nguồn Class và signer metadata nếu có | Bằng chứng mọi permission/certificate hợp lệ |

Để tránh lọt lỗi, CI/CD có thể ghi nhận checksum artifact và xác thực chúng theo release policy, kiểm tra JAR signing, kiểm tra package layout và nạp thử những class quan trọng trong môi trường gần giống production.

## 16. Không nên nhầm certificate consistency với quyền truy cập code

Ở Java hiện đại, runtime code có thể chịu nhiều cơ chế phân quyền khác nhau:

- **OS/process/container security**: quyền file/network và process isolation.
- **JPMS**: module readability, exports, opens và package ownership.
- **ClassLoader**: định danh kiểu, delegation và một số kiểm tra certificate consistency.
- **JAR signature**: integrity và signer metadata của archive/entry.
- **Application trust policy**: publisher/artifact allowlist, certificate validation, artifact attestation, sandbox process khi cần.

Một lớp được define từ signed JAR **không tự động có quyền đặc biệt**, cũng không bị chặn đọc file chỉ vì thiếu signature. Không dùng JAR signing hay package sealing làm sandbox chung để chạy plugin không tin cậy.

Nếu cần chạy third-party code chưa được trust, cách ly bằng tiến trình/VM/container cùng chính sách hệ điều hành và kiểm soát supply chain. `ClassLoader` và signer metadata là một phần của bức tranh, không phải toàn bộ mô hình phòng thủ.

## 17. Những sai lầm phổ biến

| Sai lầm | Điều cần nhớ |
| --- | --- |
| “Có file .RSA nghĩa toàn JAR chắc chắn được ký hoàn toàn” | Cần xác minh các entries thực sự được ký và bytes hiện tại |
| “jarsigner verify thành công => signer đáng tin” | Integrity verification khác trust validation |
| “Hai JAR cùng CA đều có cùng signer set” | Exact certificate sets có thể khác dù cùng CA phát hành |
| “Cùng signer => có thể trộn package sealed từ hai JAR” | Sealing kiểm tra seal base/JAR source |
| “Không ký JAR => không thể chứa Java class” | Unsigned classes hợp lệ trong nhiều ứng dụng |
| “Package certificate check áp dụng toàn JVM” | Kiểm tra trong phạm vi defining loader/package |
| “Hai class cùng package name luôn là một runtime package” | Defining loader là phần danh tính runtime package |
| “Xóa signature files là sửa được mọi lỗi” | Có thể phá integrity/provenance và vi phạm policy |
| “CodeSource URL tự chứng minh file được trust” | URL là metadata về nguồn, không phải trust decision |
| “Nếu package certificate mismatch thì chỉ việc bắt Exception” | `SecurityException` là runtime error cần sửa packaging/policy |
| “Sealing và signing là một thứ” | Sealing kiểm tra package source; signing kiểm tra integrity/signer metadata |
| “Custom defineClass bytes tự suy ra signer” | Phải giữ verified metadata qua CodeSource/ProtectionDomain phù hợp |

## 18. Bài tập tự kiểm tra

**1. Nếu trong cùng loader, package `p` đã định nghĩa class có certificate set A, class tiếp theo cùng package unsigned có hợp lệ không?**  
Không theo quy tắc `defineClass` khi set không khớp; có thể ném `SecurityException`.

**2. Hai class cùng package source nhưng do hai defining loaders riêng định nghĩa có chịu một package certificate set toàn JVM không?**  
Không. Mỗi loader có namespace/package definition riêng, dù vẫn cần xét loader constraints và quyền truy cập.

**3. Package sealed ở JAR A; JAR B cùng signer nhưng cũng chứa package đó. Có chắc cùng loader nạp được cả hai không?**  
Không. Nếu nguồn không phù hợp seal base, sealing violation có thể xảy ra.

**4. Vì sao `JarEntry.getCodeSigners()` đôi khi null trước khi đọc entry bytes?**  
Vì signature verification cho entry được thực hiện trong quá trình đọc; cần đọc hoàn chỉnh entry qua verified JarFile để có signer metadata.

**5. `jarsigner -verify` có tự quyết định certificate self-signed của bài demo được tổ chức của bạn tin cậy không?**  
Không. Trust policy là bước riêng, cần đánh giá chain/anchors và yêu cầu của hệ thống.

**6. Một fat JAR mới có thể dùng nguyên signature metadata của JAR đã bị repackage không?**  
Không nên; thay đổi bytes/manifest thường làm invalid các signature cũ hoặc khiến signer metadata không còn đúng.

**7. `Package.isSealed()` kiểm tra chữ ký số hay seal base?**  
Nó quan sát thuộc tính sealing của package, không xác minh trust signer.

**8. Hai JAR unsigned và unsealed cùng package chắc chắn luôn load được không?**  
Không tuyệt đối; vẫn còn duplicate binary names, bytecode/linkage, class loaders, dependency và module rules.

**9. Có nên truyền `null` làm binary name khi tự `defineClass` để tránh signer consistency check?**  
Không. Nên truyền tên đúng để JVM kiểm tra nhất quán tên và certificate.

**10. Nếu log chỉ có `SecurityException` mà không rõ nguyên nhân, bước đầu tiên là gì?**  
Đọc toàn stack trace/root cause, xác định class/package, loader, code source và manifest; sau đó phân biệt signer mismatch với sealing violation.

## 19. Nguồn tham khảo chính thức

- Java SE 17 — **ClassLoader** (`defineClass` và quy tắc exact certificate sets trong cùng package): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — **JarFile** (verified signed entries, signer metadata và giới hạn về certificate trust): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html
- Java SE 17 — **JarEntry** (`getCodeSigners`/`getCertificates`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarEntry.html
- Java SE 17 — **Package** (`isSealed`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html
- Java SE 17 — **CodeSource**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html
- Java SE 17 — **ProtectionDomain**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html
- Java SE 17 — **URLClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **JAR File Specification** (package sealing, signatures và manifest): https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Java SE 17 — **jarsigner command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Java SE 17 — **keytool command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html
- JVM Specification Java 17 §5.3 — Creation and Loading (runtime package/defining loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
