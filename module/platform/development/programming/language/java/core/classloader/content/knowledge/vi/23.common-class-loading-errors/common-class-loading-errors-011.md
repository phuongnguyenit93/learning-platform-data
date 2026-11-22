# SecurityException do package sealing, chứng thư hoặc package bị cấm

Khi ứng dụng Java nạp class từ JAR, `ClassLoader` có thể ném **`java.lang.SecurityException`** dù class file tồn tại, đường dẫn đúng và bytecode đã biên dịch hợp lệ. Trong chủ đề **Java core – classloader**, có ba nguyên nhân dễ bị nhầm:

1. **Package sealing violation**: loader định nghĩa các class thuộc **cùng runtime package** từ những nguồn JAR không phù hợp với quy tắc package `Sealed`.
2. **Package signer/certificate mismatch**: loader đã định nghĩa class đầu tiên trong package với **một tập chứng thư người ký**, nhưng class tiếp theo cùng package có tập chứng thư **khác** (ví dụ signed và unsigned).
3. **Prohibited package name `java.*`**: application/custom loader cố **tự định nghĩa** một class có binary name bắt đầu bằng `java.`, trong khi Java chỉ cho phép nhóm loader nền tảng được quy định làm việc này.

Ba trường hợp đều có thể biểu hiện là `SecurityException`, nhưng **quy tắc kiểm tra, nguyên nhân và cách sửa khác nhau**. Chúng cũng **không phụ thuộc vào việc SecurityManager đang được bật**: đặc biệt từ JDK 24, SecurityManager đã bị vô hiệu hóa vĩnh viễn nhưng các ràng buộc class loading trên vẫn có ý nghĩa riêng.

## 1. Những khái niệm phải tách biệt

Trước khi sửa lỗi, cần phân biệt các thuật ngữ:

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Binary class name** | Tên như `sample.api.First`, `java.demo.Forbidden`; truyền vào `ClassLoader.loadClass` và `defineClass` |
| **JAR entry name** | Đường trong archive như `sample/api/First.class`; khác binary name |
| **Defining loader** | Loader thực sự định nghĩa runtime class; có thể khác loader được gọi ban đầu do parent delegation |
| **Runtime class identity** | Cặp **(binary name, defining class loader)** |
| **Runtime package identity** | Đối với class thông thường, cặp **(package name, defining class loader)** |
| **JAR sealing** | Quy ước manifest/package nhằm buộc các class trong một package được loader nạp từ một nguồn JAR phù hợp |
| **Signer certificate set** | Tập certificates của code source gắn với class khi định nghĩa, được kiểm tra tính nhất quán trong package của loader |
| **`ProtectionDomain` / `CodeSource`** | Metadata liên quan class/code source, có thể chứa URL và certificates |
| **`SecurityManager`** | Cơ chế permission checks mang tính lịch sử, khác với các kiểm tra class definition ở đây |

Một JAR chứa `a.b.C` **không bảo đảm** class được nạp thành công: JVM/loader còn kiểm tra tên, nguồn, quyền package, chữ ký, phiên bản class file và type linking.

**Quan trọng:** Cùng tên package trong hai loader khác nhau **không phải cùng runtime package**. Điều kiện sealing và signer được đánh giá trong ngữ cảnh loader/package phù hợp, không có nghĩa mọi JAR trong toàn JVM buộc dùng chung một tập certificate.

## 2. Ba nguyên nhân SecurityException: so sánh nhanh

| Tình huống | Nguồn kiểm tra | Ví dụ | Hướng khắc phục |
|---|---|---|---|
| **Sealing violation** | JAR manifest/package metadata, loader như `URLClassLoader` | `sample.api.First` từ JAR A sealed, `sample.api.Second` từ JAR B | Đưa class cùng sealed package về đúng JAR, hoặc thiết kế lại sealing/package |
| **Signer mismatch** | `ClassLoader#defineClass` và certificate set của package | Class đầu từ signed JAR, class sau unsigned trong cùng package/loader | Ký các classes nhất quán, không trộn unsigned/signed, hoặc tách namespace/loader đúng kiến trúc |
| **`java.*` prohibited** | `ClassLoader#defineClass` và reserved platform namespace | Custom loader định nghĩa `java.demo.Forbidden` | Đổi tên package thành namespace ứng dụng; ủy quyền các classes chuẩn cho platform |
| **Legacy permission denial** | SecurityManager trong runtime cũ khi được bật | `checkPermission(new FilePermission(...))` | Kiểm tra JDK/policy cũ; **không đánh đồng** với ba lỗi trên |

Trên OpenJDK/HotSpot, stack trace hoặc message thường có cụm:

```text
sealing violation: package ... is sealed
sealing violation: can't seal package ...: already loaded
class "..."'s signer information does not match signer information of other classes in the same package
Prohibited package name: java.demo
```

Đây là **các mẫu thông điệp chẩn đoán**, không phải chuỗi cố định được mọi Java implementation cam kết. Có thể có khác biệt về chữ hoa, dấu câu, stack trace, phiên bản JDK và framework. **Dựa vào exception class, root cause và classloader/code source**, đừng viết chương trình bắt lỗi bằng cách so khớp nguyên văn message.

## 3. Package sealing là gì?

Trong **JAR File Specification**, một package có thể được khai báo **sealed**. Với loader hỗ trợ JAR manifest sealing, mục đích là bảo đảm các class được **loader đó** định nghĩa trong package ấy đến từ **cùng nguồn JAR** theo quy tắc sealing.

Ví dụ JAR A:

```text
a.jar
├── META-INF/
│   └── MANIFEST.MF
└── sample/
    └── api/
        └── First.class
```

Manifest:

```text
Manifest-Version: 1.0
Sealed: true

```

JAR B:

```text
b.jar
└── sample/
    └── api/
        └── Second.class
```

Nếu **cùng một `URLClassLoader`** nạp `sample.api.First` từ A và sau đó cố nạp `sample.api.Second` từ B, package `sample.api` đã được ghi nhận là sealed với nguồn A; lớp của B không đến từ seal base tương ứng. Loader có thể ném `SecurityException`.

**Không phải lỗi tên package trùng tự thân.** Nếu hai JAR đều không sealed và có cùng package, trong mô hình classpath/unnamed module thông thường, chúng có thể cùng cung cấp các class **khác binary name** trong cùng runtime package — tuy nhiên vẫn còn những ràng buộc độc lập như signer certificates hoặc module resolution.

### 3.1. Manifest khai báo sealing toàn JAR

Đặt ở **main section**:

```text
Manifest-Version: 1.0
Sealed: true

```

`Sealed: true` mặc định áp dụng cho các packages trong JAR, trừ những package có override riêng trong individual manifest sections.

`Sealed: false` hoặc không có thuộc tính `Sealed` thường dẫn đến package không sealed, theo quy tắc specification và package-level override.

### 3.2. Chỉ seal một package

Một manifest có thể cấu hình cụ thể:

```text
Manifest-Version: 1.0

Name: sample/api/
Sealed: true

```

Lưu ý:

- `Name: sample/api/` là **package directory entry name**, dùng dấu `/` và dấu `/` cuối.
- Dòng trống phân tách **main section** và individual section.
- Đây là dữ liệu **manifest**, không phải Java source.
- Các package khác không tự trở thành sealed chỉ vì một package được đánh dấu `Sealed: true`.

Một pattern khác:

```text
Manifest-Version: 1.0
Sealed: true

Name: sample/api/
Sealed: false

```

có nghĩa mọi package mặc định sealed, **riêng `sample.api` được ghi đè thành unsealed**. Không tự viết các section sai cú pháp hoặc quên dòng kết thúc; hãy kiểm tra `META-INF/MANIFEST.MF` sau khi build.

### 3.3. Ai thực thi sealing?

**Sealing theo JAR manifest là hành vi của cơ chế loader/packaging**, điển hình `URLClassLoader` khi mở JARs và xử lý package metadata. `ClassLoader#defineClass` ở mức thấp **không tự đọc manifest hay tự xác định JAR seal base** chỉ từ một mảng `byte[]`.

Nếu bạn tự viết custom loader đọc bytes rồi gọi `defineClass`, cần quyết định cách:

1. Đọc manifest/package attributes.
2. Định nghĩa package metadata bằng `definePackage` khi cần.
3. So sánh nguồn class tiếp theo với seal base.
4. Kiểm tra signer certificates/`CodeSource` đúng quy tắc.

Dựa vào `defineClass` trần rồi tuyên bố “đã thực thi JAR sealing” là sai. Ngược lại, **không nên bỏ qua package metadata khi viết custom loader production** có nhiệm vụ tương đương loader JAR chuẩn.

## 4. Demo Java 17+: sealing, package cấm và class loading đúng/sai

Bài tập tạo hai JAR cùng package `sample.api` nhưng mỗi JAR chứa class **khác tên**, một class thử nghiệm thuộc `java.demo` và một chương trình chính nạp qua loader riêng.

Cấu trúc nguồn/output:

```text
package-security-demo/
├── src/
│   ├── one/sample/api/First.java
│   ├── two/sample/api/Second.java
│   ├── java/demo/Forbidden.java
│   └── app/PackageFailures.java
├── sealed.mf
├── out/
│   ├── one/
│   ├── two/
│   ├── forbidden/
│   └── app/
└── dist/
```

### 4.1. Class ở JAR thứ nhất

Tệp **`src/one/sample/api/First.java`**:

```java
package sample.api;

public class First {
    public static String name() {
        return "first";
    }
}
```

### 4.2. Class ở JAR thứ hai

Tệp **`src/two/sample/api/Second.java`**:

```java
package sample.api;

public class Second {
    public static String name() {
        return "second";
    }
}
```

Hai class thuộc **cùng package name `sample.api`** nhưng **khác binary name**. Điều này làm rõ sealing/signing failure thay vì một lỗi duplicate definition của đúng cùng class.

### 4.3. Class thử nghiệm ở namespace cấm

Tệp **`src/java/demo/Forbidden.java`**:

```java
package java.demo;

public class Forbidden {
}
```

**Chỉ dùng làm tình huống học tập.** Code ứng dụng thực không được đặt dưới namespace `java.*`. Trong bài thử này, `javac --release 17` có thể tạo file `java/demo/Forbidden.class` trên JDK được sử dụng; việc biên dịch không cấp quyền để **application-defined loader định nghĩa runtime class** mang tên ấy.

### 4.4. Chương trình chạy thử

Tệp **`src/app/PackageFailures.java`**:

```java
package app;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PackageFailures {
    static final class BytesLoader extends ClassLoader {
        BytesLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent =
                PackageFailures.class.getClassLoader();

        URL[] urls = {
            Path.of(args[0]).toUri().toURL(),
            Path.of(args[1]).toUri().toURL()
        };

        try (URLClassLoader loader =
                new URLClassLoader(urls, parent)) {
            Class<?> first = loader.loadClass(
                    "sample.api.First");

            System.out.println("First loader: "
                    + (first.getClassLoader() == loader));

            try {
                loader.loadClass("sample.api.Second");
                System.out.println("Second: loaded");
            } catch (SecurityException ex) {
                System.out.println("Second: SecurityException");
            }
        }

        BytesLoader own = new BytesLoader(parent);
        byte[] bytes = Files.readAllBytes(Path.of(args[2]));

        try {
            own.define("java.demo.Forbidden", bytes);
            System.out.println("Forbidden: loaded");
        } catch (SecurityException ex) {
            System.out.println("Forbidden: SecurityException");
        }
    }
}
```

**Vai trò hai loader:**

- `URLClassLoader` kiểm tra JAR/package metadata khi tìm classes từ các URLs.
- `BytesLoader` cố ý gọi `defineClass` trực tiếp để chứng minh **namespace `java.*` vẫn bị kiểm tra**, dù không có JAR manifest hay SecurityManager.
- `First` được load **trước `Second`** để xác lập trạng thái runtime package, rồi tình huống thứ hai bộc lộ sealing hoặc signer mismatch.

Trong thực tế phải kiểm tra `args.length` và báo usage khi thiếu tham số; ví dụ được chạy với chính xác ba arguments bên dưới. Catch `SecurityException` ở đây phục vụ **đo lường lỗi**. **Không nên nuốt lỗi trong plugin manager production** rồi coi plugin đã tải thành công.

### 4.5. Manifest sealing

Tệp **`sealed.mf`**:

```text
Manifest-Version: 1.0
Sealed: true

```

Đây là manifest nhập cho công cụ `jar`. Dòng trống cuối phân định hoàn tất main section.

### 4.6. Lệnh biên dịch và đóng JAR (Bash)

Từ thư mục `package-security-demo`, dùng JDK 17+:

```bash
mkdir -p out/one out/two out/forbidden out/app dist

javac --release 17 -d out/one src/one/sample/api/First.java
javac --release 17 -d out/two src/two/sample/api/Second.java
javac --release 17 -d out/forbidden src/java/demo/Forbidden.java
javac --release 17 -d out/app src/app/PackageFailures.java

# JAR A có package sealed.
jar --create --file dist/one-sealed.jar \
  --manifest sealed.mf -C out/one .

# JAR A không có sealing (JAR dành cho đối chiếu).
jar --create --file dist/one-open.jar -C out/one .

# JAR B không có sealing.
jar --create --file dist/two-open.jar -C out/two .

# Trường hợp 1: sealed A + B chứa cùng package.
java -cp out/app app.PackageFailures \
  dist/one-sealed.jar dist/two-open.jar \
  out/forbidden/java/demo/Forbidden.class

# Trường hợp 2: cả A và B đều không sealed.
java -cp out/app app.PackageFailures \
  dist/one-open.jar dist/two-open.jar \
  out/forbidden/java/demo/Forbidden.class
```

### 4.7. Lệnh tương đương trong PowerShell

Từ cùng thư mục, với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out/one, out/two, out/forbidden, out/app, dist | Out-Null

javac --release 17 -d out/one src/one/sample/api/First.java
javac --release 17 -d out/two src/two/sample/api/Second.java
javac --release 17 -d out/forbidden src/java/demo/Forbidden.java
javac --release 17 -d out/app src/app/PackageFailures.java

jar --create --file dist/one-sealed.jar --manifest sealed.mf -C out/one .
jar --create --file dist/one-open.jar -C out/one .
jar --create --file dist/two-open.jar -C out/two .

java -cp out/app app.PackageFailures dist/one-sealed.jar dist/two-open.jar out/forbidden/java/demo/Forbidden.class
java -cp out/app app.PackageFailures dist/one-open.jar dist/two-open.jar out/forbidden/java/demo/Forbidden.class
```

Các lệnh có thể dùng cùng JDK 17+ khi `java`, `javac` và `jar` nằm trên PATH.

### 4.8. Đầu ra được kiểm chứng

**Trường hợp 1 — A sealed, B unsealed:**

```text
First loader: true
Second: SecurityException
Forbidden: SecurityException
```

**Trường hợp 2 — A và B đều unsealed:**

```text
First loader: true
Second: loaded
Forbidden: SecurityException
```

Ví dụ đã được biên dịch với **`javac --release 17`**, đóng JAR bằng `jar` và chạy thành công trên **OpenJDK 24**. Các chuỗi ở trên là stdout của chính mã thử nghiệm, không phải nội dung stack trace của `SecurityException`.

**Kết luận từ đối chứng:**

1. Hai JAR unsealed có thể cung cấp hai classes khác tên trong cùng package, cùng defining loader, khi các điều kiện còn lại thỏa.
2. Seal package từ JAR A khiến class cùng runtime package từ nguồn B bị từ chối.
3. Dù sealing được bật hay không, custom `BytesLoader` vẫn không được định nghĩa tên `java.demo.Forbidden`.
4. `SecurityException` xuất hiện **không có nghĩa SecurityManager được bật**.
5. Bỏ sealing không sửa lỗi package `java.*`, vì đó là **một kiểm tra độc lập**.

## 5. Vì sao thứ tự nạp class có thể làm thông điệp khác đi?

Với `URLClassLoader`, package metadata được kiểm tra khi loader định nghĩa class trong package.

### Tình huống A — package bắt đầu sealed

```text
load sample.api.First từ sealed a.jar
   |
   +--> package sample.api: sealed với a.jar
   |
load sample.api.Second từ b.jar
   |
   +--> vi phạm seal base -> SecurityException
```

### Tình huống B — package bắt đầu unsealed, JAR sau muốn seal

```text
load sample.api.Second từ unsealed b.jar
   |
   +--> package sample.api: không sealed
   |
load sample.api.First từ sealed a.jar
   |
   +--> không được “seal ngược” package đã được định nghĩa khác policy
   |
   +--> SecurityException
```

Cả hai đều là sealing violations nhưng message khác. Không sửa bằng cách xáo thứ tự JAR “cho chạy” mà chưa hiểu contract: đổi thứ tự chỉ có thể đổi **lớp nào thắng** hoặc điểm kiểm tra bị lỗi.

Một vấn đề khác là **duplicate class**: nếu hai JAR đều chứa `sample/api/First.class` và chỉ dùng cùng một loader, loader có thể chọn bản đầu tiên theo lookup policy. Điều đó **không phải** lỗi sealing chỉ vì duplicate file; cần phân biệt với những classes **khác nhau trong cùng sealed package**.

## 6. Certificate/signer mismatch là lỗi độc lập với sealing

Ngoài package sealing, **`ClassLoader#defineClass`** kiểm tra tính nhất quán của certificate set trong package của **một defining loader**.

Theo Java SE 17 JavaDoc:

- **Class đầu tiên** được loader định nghĩa trong một package quyết định **tập certificates của package đó**.
- Các classes tiếp theo do **cùng loader** định nghĩa trong cùng package cần có **cùng tập certificates**.
- Tập certificates lấy từ **`CodeSource` của `ProtectionDomain`** gắn với class.
- Nếu tập certificates không khớp, `defineClass` có thể ném **`SecurityException`**.
- Khi overload `defineClass` nhận `name = null`, một số kiểm tra theo tên không được thực hiện theo JavaDoc; **không nên dùng `null` làm thủ thuật né kiểm tra**. Hãy cung cấp đúng binary name khi định nghĩa class.

Ví dụ:

```text
loader L:
  sample.api.First  từ one-signed.jar    [certificate set S]
  sample.api.Second từ two-open.jar      [unsigned/empty set]
         |
         v
      SecurityException
      vì signer information không nhất quán
```

Điểm quan trọng: **Một package có thể không sealed mà vẫn vi phạm signer consistency**. Sealing liên quan **nguồn JAR/seal base**; signer mismatch liên quan **tập chứng thư người ký**. Hai kiểm tra không phải một.

### Signer certificate không phải “mức độ tin cậy toàn cục”

Certificate set dùng cho package consistency là thông tin người ký gắn với code source. Nó không có nghĩa:

- JVM tự xác nhận mọi certificate đều được một CA công khai đáng tin cậy cấp.
- Hai JAR cùng certificate signer đã được tổ chức bạn cho phép chạy.
- Chữ ký JAR thay thế việc kiểm tra dependency provenance, vulnerability và update pipeline.
- Signed JAR tự động bảo vệ plugin trước mọi hành vi độc hại.

Một JAR được ký bằng **self-signed certificate để thử nghiệm** có thể đi qua bước xử lý người ký, nhưng không nên coi đó là bằng chứng trust trong production.

### Signed và unsigned có thể trộn trong cùng package không?

Với **cùng defining loader**, nếu một class đầu có non-empty signer certificates còn class tiếp theo trong cùng runtime package là unsigned, các sets khác nhau, nên có thể gặp `SecurityException`.

Nếu hai plugin được định nghĩa bởi **hai class loaders riêng biệt** và **không share chính runtime package**, kiểm tra giữa classes từ hai defining loaders không phải cùng package của loader. Tuy vậy những objects/types do hai loader tạo cũng không tự tương thích. **Tách loader để tránh lỗi** chỉ đúng khi phù hợp kiến trúc class identity và API boundary; không thay cho signing policy đúng.

## 7. Thực hành tùy chọn: tái hiện signer mismatch với JDK tools

Phần 4 đã tạo `dist/one-open.jar` và `dist/two-open.jar` — cả hai đều **không sealed**. Ta ký **chỉ** JAR đầu bằng một certificate thử nghiệm, để tách nguyên nhân signer khỏi sealing.

Từ thư mục bài thực hành:

```bash
# CHỈ DÙNG CHO THỬ NGHIỆM CỤC BỘ.
# "changeit" là mật khẩu demo công khai, tuyệt đối không dùng
# cho khóa ký thực tế hoặc môi trường production.
keytool -genkeypair \
  -alias lesson \
  -keyalg RSA \
  -keysize 2048 \
  -storetype PKCS12 \
  -keystore demo-test.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=Lesson Test" \
  -validity 2 \
  -noprompt

# Ký JAR thứ nhất, giữ bản JAR thứ hai unsigned.
jarsigner \
  -keystore demo-test.p12 \
  -storepass changeit \
  -keypass changeit \
  -signedjar dist/one-signed.jar \
  dist/one-open.jar lesson

# Xác nhận JAR có signature metadata.
jarsigner -verify dist/one-signed.jar

# Nạp class đầu từ signed JAR, class sau từ unsigned JAR.
java -cp out/app app.PackageFailures \
  dist/one-signed.jar dist/two-open.jar \
  out/forbidden/java/demo/Forbidden.class
```

Trên **PowerShell**, viết các lệnh dài trên một dòng hoặc dùng ký hiệu tiếp dòng hợp lệ của PowerShell, không dùng dấu `\` cuối dòng kiểu Bash:

```powershell
keytool -genkeypair -alias lesson -keyalg RSA -keysize 2048 -storetype PKCS12 -keystore demo-test.p12 -storepass changeit -keypass changeit -dname "CN=Lesson Test" -validity 2 -noprompt

jarsigner -keystore demo-test.p12 -storepass changeit -keypass changeit -signedjar dist/one-signed.jar dist/one-open.jar lesson

jarsigner -verify dist/one-signed.jar

java -cp out/app app.PackageFailures dist/one-signed.jar dist/two-open.jar out/forbidden/java/demo/Forbidden.class
```

**Đầu ra của chương trình** được kiểm chứng trên JDK 24:

```text
First loader: true
Second: SecurityException
Forbidden: SecurityException
```

Ở lần này:

- `sample.api.First` lấy từ **JAR đã ký**, nhưng **không sealed**.
- `sample.api.Second` lấy từ **JAR chưa ký**, cùng runtime package của loader.
- Việc nạp class thứ hai ném `SecurityException` vì **signer information khác nhau**, không phải do sealing.
- Lỗi `Forbidden` vẫn độc lập và được tái hiện lần thứ ba.

**Cảnh báo về `jarsigner -verify`:** Với self-signed test certificate, công cụ có thể in `jar verified` **kèm warnings** về chuỗi trust/PKIX, certificate gần hết hạn và không có trusted timestamp. Đây là hành vi hợp lý trong bài test, **không được dùng ký tự “jar verified” riêng lẻ để chứng nhận độ tin cậy của phần mềm**.

Không commit, xuất bản hoặc tái sử dụng keystore test với password `changeit`. Production signing phải có key management, trust policy, signature verification và secret handling riêng.

### Nếu muốn thấy nguyên nhân chi tiết

Trong demo, thay tạm catch:

```java
} catch (SecurityException ex) {
    System.out.println("Second: SecurityException");
}
```

bằng:

```java
} catch (SecurityException ex) {
    ex.printStackTrace();
}
```

Đây là **đoạn thay thế minh họa** trong method của demo, không phải chương trình độc lập. Khi chạy, stack trace sẽ giúp phân biệt sealing verification ở `URLClassLoader` với signer check ở `ClassLoader#defineClass`. Không hard-code đầy đủ stack trace vào lesson vì phiên bản JDK/vendor khác nhau.

## 8. Package bị cấm java.*: không liên quan sealing hay chứng thư

Giới hạn thứ ba xuất hiện tại `ClassLoader#defineClass`. Với ordinary application/custom loader, tên như:

```text
java.demo.Forbidden
java.lang.MyString
java.util.CustomCollections
```

đều bắt đầu bằng `java.`, nên không được tự định nghĩa.

Java SE 17 JavaDoc phát biểu cụ thể: class có tên bắt đầu `java.` chỉ được **platform class loader hoặc các loader tổ tiên của nó** định nghĩa. Điều này không đồng nghĩa “bất kỳ loader nào có parent là platform loader đều được phép”; một loader do ứng dụng tạo là **child**, không phải platform/ancestor.

### loadClass được phép khác defineClass bị cấm

```java
ClassLoader pluginLoader = new ClassLoader(
        ClassLoader.getSystemClassLoader()) {
};

Class<?> core = pluginLoader.loadClass("java.lang.String");
System.out.println(core == String.class);
```

Đây là một đoạn minh họa hợp lệ bên trong method, **không có `main` riêng**. `loadClass` mặc định ủy quyền parent để nhận `String` do runtime định nghĩa, nên phép so sánh thường là `true` trên JVM tiêu chuẩn.

Ngược lại, `BytesLoader` trong demo gọi:

```java
own.define("java.demo.Forbidden", bytes);
```

và bị `SecurityException` vì muốn **loader riêng tự định nghĩa một class mới trong namespace `java.*`**.

**Lưu ý:** Compile ra file `java/demo/Forbidden.class` không đồng nghĩa JVM cho phép application loader nạp class ấy; compile-time và runtime class definition có những kiểm tra khác nhau.

### Không nên “sửa” bằng cách đổi thành javax.* hoặc jdk.*

Quy tắc `java.*` ở `defineClass` là một ràng buộc được công bố cụ thể. Nhưng tên `javax.*`, `jdk.*`, `sun.*` cũng thường được gắn với platform/JDK/framework và có thể chịu module/package access hoặc các restriction khác. **Không chiếm dụng namespace của hệ sinh thái** chỉ để vượt một check.

Hãy dùng package riêng, ví dụ:

```java
package com.example.plugin;
```

Đây là package declaration minh họa. Đặt tên package theo miền/đơn vị sở hữu code, tránh xung đột với platform.

## 9. Sự liên quan của defining loader, parent delegation và runtime package

Từ góc nhìn JVM, một runtime package thông thường được xác định bởi:

```text
(package name, defining class loader)
```

Ví dụ:

```text
Loader A defines sample.api.First
Loader B defines sample.api.Second
    |
    +--> cùng package name "sample.api"
    +--> KHÁC defining loader
    +--> KHÁC runtime package
```

Hệ quả:

- Hai classes không tự có cùng **package-private access**, dù source code ghi cùng `package sample.api;`.
- Một package được sealed trong URLClassLoader A không tự làm package cùng tên của loader B thành cùng sealed package.
- Package signer consistency được áp dụng trong ngữ cảnh định nghĩa class của loader; không có nghĩa signer của mọi class cùng tên package **trên toàn JVM** phải giống nhau.
- Nếu host truyền một class private API từ loader A sang loader B, có thể nảy sinh `ClassCastException`, `IllegalAccessError` hoặc `LinkageError` tùy tình huống.

**Không dùng per-plugin loader làm mẹo duy nhất để giấu sealing/signature problems.** Nó có thể làm giảm xung đột package giữa plugin versions khi đúng kiến trúc, nhưng cũng tạo namespace/type boundaries phải quản lý cẩn thận.

### Trường hợp parent thắng child

Nếu parent loader đã định nghĩa `sample.api.First`, một child `URLClassLoader` parent-first có thể trả class từ parent thay vì tự định nghĩa bản trong plugin JAR. Khi đó kiểm tra package/sealing/signers của child liên quan đến **những classes child thực sự định nghĩa**, không phải tất cả class names được gọi trên child qua `loadClass`.

Hãy kiểm tra:

```java
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
```

Đây là snippet có biến `Class<?> type` trong method, không phải chương trình riêng. Đừng suy luận defining loader chỉ từ biến đã gọi `loader.loadClass(...)`.

## 10. Điều gì xảy ra với custom ClassLoader tự viết?

Một loader tự đọc bytes:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] data = loadBytesFromTrustedSource(name);
    return defineClass(name, data, 0, data.length);
}
```

Đây là **mẫu pseudocode Java**, vì `loadBytesFromTrustedSource` chưa được định nghĩa.

Từ góc nhìn security/package rules:

- `defineClass` vẫn có **các kiểm tra như tên `java.*` và signer certificate set**.
- Nếu truyền `ProtectionDomain`, `CodeSource` mang certificate data thích hợp theo contract; không tự giả mạo/đổi certificates để “cho chạy”.
- `defineClass` không tự biết **manifest sealing** của mọi nguồn bytes nếu loader không cung cấp package metadata/verification tương ứng.
- Không định nghĩa lại cùng binary name trong cùng loader; tình huống đó là **duplicate definition/`LinkageError`** khác.
- Nếu bytecode không đúng định dạng, có thể có `ClassFormatError` hoặc `VerifyError`; đừng biến mọi lỗi thành `SecurityException` hoặc `ClassNotFoundException`.
- Nếu name truyền vào khác class name trong bytes, có thể có `NoClassDefFoundError`; đó không phải package sealing.

Với ứng dụng cần JAR loading chuẩn, **`URLClassLoader`** là lựa chọn thực tiễn hơn việc tự xây toàn bộ package verification. Với hệ sinh thái plugin lớn, có thể dùng module/plugin manager sẵn có và thiết kế package namespace rõ ràng.

## 11. Chẩn đoán thực tế: từ exception tới nguyên nhân gốc

Khi gặp `SecurityException` trong class loading, một quy trình hiệu quả:

1. **Đọc stack trace đầy đủ.** Lỗi xuất hiện khi `URLClassLoader` kiểm tra sealing, hay ở `ClassLoader#defineClass` kiểm tra certificates/namespace?
2. **Xác định binary name thật sự.** Có bắt đầu bằng `java.` không? Có thuộc package đã có class trước đó không?
3. **Xác định defining loader.** Đừng đoán từ tên class hoặc JAR path. Ghi class loader object identity của những class nạp thành công.
4. **Kiểm tra thứ tự load.** Class nào trong package đã được định nghĩa trước, từ JAR nào?
5. **Kiểm tra manifest của từng JAR.** Có `Sealed: true` ở main hoặc package-specific section không?
6. **Kiểm tra JAR signing.** JAR đầu signed nhưng JAR sau unsigned? Có certificate sets khác nhau không? Có signature verification error không?
7. **Phân biệt tài nguyên/JAR trùng tên.** Hai JAR có cùng package nhưng khác class name khác với duplicate binary class name.
8. **Kiểm tra classpath/module path thực tế.** Loader nào thấy những JAR nào? Parent-first/child-first có tác động không?
9. **Không bật SecurityManager để sửa.** Lỗi sealing/signing/package reservation vẫn có thể xảy ra khi manager vắng mặt.
10. **Sửa nguồn gốc.** Đồng bộ package/JAR boundaries, signing policy hoặc namespace; không catch rồi bỏ qua lỗi.

### Kiểm tra manifest bằng công cụ JDK

```bash
jar --list --file dist/one-sealed.jar
jar --list --file dist/two-open.jar
```

`jar --list` xác nhận class entries và manifest entry, nhưng **không tự in nội dung manifest**. Để xem `META-INF/MANIFEST.MF`, dùng archive viewer hoặc giải nén **vào một thư mục tạm riêng**:

```bash
mkdir -p manifest-inspect
cd manifest-inspect
jar --extract --file ../dist/one-sealed.jar META-INF/MANIFEST.MF
```

Đây là lệnh ví dụ Bash trong thư mục bài thử; vị trí tương đối `../dist/...` giả định `manifest-inspect` nằm cạnh `dist`. Sau khi mở file text, kiểm tra `Sealed` và các package sections.

### Kiểm tra signing

```bash
jarsigner -verify -verbose -certs dist/one-signed.jar
```

Lệnh có thể cho biết ký số và cảnh báo về certificate chain/timestamp. **Một JAR verified về tính toàn vẹn không tự đồng nghĩa mọi signer được tin cậy**; kiểm tra tin cậy phải dựa vào trust store/PKI policy thực tế.

Nếu cần inspect class metadata khi đã load thành công:

```java
Class<?> type = loader.loadClass("sample.api.First");
System.out.println("Class: " + type.getName());
System.out.println("Defining loader: " + type.getClassLoader());

Package pkg = type.getPackage();
System.out.println("Package sealed: "
        + (pkg != null && pkg.isSealed()));

var pd = type.getProtectionDomain();
var source = pd == null ? null : pd.getCodeSource();
System.out.println("Code source: "
        + (source == null ? "(unknown)" : source.getLocation()));
```

Đây là snippet minh họa trong method có biến `loader`. `Package.isSealed()` cho biết package metadata; `CodeSource.getLocation()` là thông tin nguồn code khi có sẵn, **không phải chứng nhận tin cậy**. Cũng có thể có `null` tùy class/runtime.

Với certificates, `CodeSource.getCertificates()` có thể trả mảng hoặc `null`. Không dùng `toString()`, thứ tự URL hay certificate count đơn thuần làm tiêu chí xác thực an ninh.

## 12. Cách sửa đúng theo từng loại lỗi

### A. Sealing violation

**Sửa tốt:** Đặt tất cả classes thuộc sealed package vào JAR/seal base thống nhất theo hợp đồng; hoặc xem lại việc có thật cần sealing không. Một project cố tình chia package `sample.api` qua nhiều JAR nên **không** seal package ấy bằng một JAR rồi nạp phần còn lại từ JAR khác qua cùng loader.

Các lựa chọn tùy kiến trúc:

- Gom các classes trong cùng sealed package về một JAR nhất quán.
- Tách packages theo artifact/module/plugin ownership để tránh split package.
- Bỏ/đổi `Sealed` **chỉ khi đáp ứng yêu cầu đóng gói và bảo mật**, không làm để che một deployment sai.
- Với plugin độc lập, dùng loader riêng nếu type boundaries và shared API đã được thiết kế rõ.
- Đặt build validation kiểm tra manifest và package split trước triển khai.

**Sai lầm:** Xóa một exception catch hoặc đảo thứ tự JAR mà không điều chỉnh cấu trúc package/source.

### B. Signer certificate mismatch

**Sửa tốt:** Dùng chính sách ký JAR thống nhất cho các classes cùng runtime package/defining loader. Ví dụ nếu cần signed packages, bảo đảm những classes cùng package có **cùng signer certificate set phù hợp**, và tách unsigned dependencies sang package khác khi thích hợp.

Có thể:

- Thống nhất signing key/certificate pipeline hợp lệ cho packages chung.
- Kiểm tra JAR sau build đã bị repack/shade làm signature metadata mất hiệu lực chưa.
- Không trộn unsigned and signed entries dưới cùng runtime package của một loader.
- Tránh trùng package giữa third-party libraries có provenance/signing khác nhau.
- Kiểm tra signer trust, expiration, timestamp/chain validation **ngoài** yêu cầu consistency để bảo đảm security thật.

**Sai lầm:** Đặt một self-signed certificate mới cho từng JAR rồi nghĩ “cả hai signed là đủ”. Hai certificate sets khác nhau vẫn có thể vi phạm package consistency.

### C. Package `java.*` bị cấm

**Sửa tốt:** Đặt class ứng dụng vào namespace sở hữu bởi bạn, ví dụ `com.example.plugin`, và **để platform loaders cung cấp classes chuẩn**.

- Không tự định nghĩa `java.lang.String` hoặc `java.foo.Helper` từ ordinary application loader.
- Không hy vọng đổi parent loader thành platform loader là đã có quyền định nghĩa tên `java.*`.
- Không dùng flags `--add-opens`/`--add-exports` để “cấp quyền” cho `defineClass` trong namespace `java.*`; các flags này nói về module access.
- Kiểm tra bytecode generators/shading/relocation đã đổi binary name sai chưa.

**Sai lầm:** Tự override `loadClass` child-first và cho rằng điều đó vô hiệu hóa `defineClass` security checks.

## 13. Phân biệt với những lỗi khác

| Lỗi | Điểm khác với ba nguyên nhân SecurityException |
|---|---|
| `ClassNotFoundException` | Loader được yêu cầu không tìm được class theo lookup contract |
| `NoClassDefFoundError` | JVM cần một class mà không giải quyết được (hoặc class đã khởi tạo thất bại); cũng có thể do tên class-file không khớp |
| `ClassFormatError` | Bytes không đúng cấu trúc class file |
| `VerifyError` | Bytecode không đáp ứng quy tắc verifier |
| `UnsupportedClassVersionError` | Class file có version mới hơn runtime hỗ trợ |
| `LinkageError` | Có thể do duplicate class definition hoặc loading constraints; không nhất thiết sealing |
| `IllegalAccessError` | Quy tắc JVM access/package/module không cho phép truy cập member/type |
| `ClassCastException` | Runtime types không tương thích, thường gặp ở loader boundary |
| `InaccessibleObjectException` | Deep reflection bị giới hạn theo JPMS/open package, không phải JAR sealing |
| `JarException` / `ZipException` | Lỗi archive/ZIP/JAR data, khác signer consistency theo package |

Một cùng stack trace có thể chứa nhiều lớp exception: đọc **root cause** và diễn biến loader. Không “fix” `SecurityException` bằng cách chỉ thêm dependency vào classpath, và không “fix” `ClassNotFoundException` bằng cách bỏ sealing khi nguồn class chưa được tìm thấy.

## 14. SecurityManager có liên quan không?

Theo **JEP 411**, `SecurityManager` được **deprecated for removal** từ JDK 17; theo **JEP 486**, nó **permanently disabled** từ JDK 24. Những quy tắc package namespace, JAR sealing và certificate consistency vẫn là cơ chế riêng của class loading/packaging.

Vì vậy:

- Một `SecurityException` trong demo được tái hiện trên **JDK 24**, nơi `SecurityManager` không thể được bật theo mô hình cũ.
- `ProtectionDomain` và `CodeSource` vẫn có vai trò metadata/signers nhất định, nhưng không nên suy luận chúng tự bật legacy permission sandbox.
- Package sealing và signer checking **không bảo đảm plugin đáng tin hoặc không đọc file/network**.
- `ClassLoader` riêng giúp runtime type/dependency isolation, **không phải process/OS sandbox**.
- Với code plugin không đáng tin, cần process/container/OS permissions, resource limits và IPC contracts riêng.

Điều kiện security trong class loading **khác** bài toán authorization nghiệp vụ và giới hạn quyền OS.

## 15. Checklist kiểm thử dành cho plugin/JAR build

Để tránh phát hiện lỗi lúc production:

- [ ] Mỗi module/plugin có package namespaces thuộc sở hữu rõ ràng.
- [ ] Không sinh hoặc relocate application classes vào `java.*`.
- [ ] Không có split sealed package qua nhiều JAR trong cùng loader.
- [ ] Manifest `Sealed` toàn JAR và theo package đã được kiểm tra sau build.
- [ ] Signer certificate set của classes cùng runtime package thống nhất theo policy.
- [ ] Không vô tình trộn unsigned plugin classes với signed package của vendor.
- [ ] JAR signing verification/trust checks được thực hiện riêng, không chỉ nhìn signer count.
- [ ] Parent delegation và plugin-private class isolation được xác minh.
- [ ] Có test với nhiều JAR cùng package nhưng khác class names.
- [ ] Có test signer mismatch (trong môi trường thử nghiệm riêng) nếu ứng dụng dùng signed JARs.
- [ ] Có log defining loader và code source khi class load thất bại.
- [ ] Không catch `SecurityException` rồi âm thầm fallback sang class có cùng tên từ nguồn thiếu tin cậy.
- [ ] Đã thử trên JDK/version/module path thực tế.
- [ ] Có kế hoạch cho package migration, không chỉ đổi URL classpath order.

## 16. Câu hỏi tự kiểm tra

**1. Hai JAR không sealed cùng chứa các class khác tên trong package `sample.api`. Có tự động ném SecurityException không?** Không; nếu cùng loader, việc dùng chung package không tự gây sealing violation. Tuy nhiên signer certificates hoặc constraints khác có thể vẫn gây lỗi.

**2. `Sealed: true` ở main section có nghĩa gì?** Mặc định đánh dấu các packages trong JAR là sealed, trừ các package-level overrides.

**3. Có thể chỉ seal `sample.api` không?** Có, dùng individual manifest section với `Name: sample/api/` và `Sealed: true`.

**4. `URLClassLoader` nạp class đầu từ sealed JAR A rồi class sau cùng package từ JAR B. Lỗi chính là gì?** Vi phạm seal base/source consistency, thường là `SecurityException`.

**5. Signed JAR A và unsigned JAR B, cùng loader/cùng package, cả hai unsealed. Có thể ném SecurityException không?** Có, do certificate/signer set không nhất quán.

**6. Nếu hai JAR đều signed thì chắc chắn không mismatch?** Không. Các classes cùng runtime package cần certificate set tương thích/giống nhau theo kiểm tra của loader, không chỉ đều có chữ ký.

**7. `java.demo.Forbidden` không có trong JDK tiêu chuẩn, custom loader có tự định nghĩa được không?** Không; tên bắt đầu `java.` bị giới hạn theo `defineClass`.

**8. Vì sao `child.loadClass("java.lang.String")` thường được phép?** Child ủy quyền để nhận class do loader nền tảng phù hợp định nghĩa, không tự tạo class cùng tên.

**9. Lỗi SecurityException từ sealing có chứng minh SecurityManager đang bật không?** Không. Đây là kiểm tra classloader/JAR độc lập.

**10. Tách hai plugin vào loader riêng có làm classes cùng package trở thành cùng runtime package không?** Không. Runtime package còn phụ thuộc defining loader.

**11. `CodeSource.getLocation()` là bằng chứng JAR đáng tin không?** Không. Nó là metadata nguồn; trust/integrity cần được kiểm tra riêng.

**12. Nếu dùng raw `defineClass` với bytes đọc từ JAR, sealing tự có hiệu lực không?** Không thể mặc định; custom loader phải xử lý package manifest/sealing policy phù hợp.

## 17. Tài liệu tham khảo chính thức

- **Java SE 17 — `ClassLoader#defineClass`:** các kiểm tra `SecurityException` khi certificates không đồng nhất hoặc tên bắt đầu `java.`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — JAR File Specification, Package Sealing:** main/per-entry `Sealed` attributes và quy tắc cùng JAR: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- **Java SE 17 — `URLClassLoader`:** nạp class từ URL/JAR và package metadata: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **Java SE 17 — `Package.isSealed`:** metadata của package: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html
- **Java SE 17 — `CodeSource` / `ProtectionDomain`:** nguồn code, certificates và domain: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html
- **Java SE 17 — Công cụ `jarsigner`:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- **JEP 411 và JEP 486:** https://openjdk.org/jeps/411 và https://openjdk.org/jeps/486

**Ghi nhớ:** Gặp `SecurityException` trong class loading, hãy hỏi **lỗi do manifest sealing, do signer certificates, hay do namespace `java.*`?** Sealing và signer consistency thường liên quan classes **cùng package do cùng loader định nghĩa**; reserved package `java.*` là hạn chế riêng tại `defineClass`. Sửa đúng nguồn gốc và kiểm tra classloader, manifest, signing policy — không dùng SecurityManager hoặc bắt bỏ exception để che lỗi.
