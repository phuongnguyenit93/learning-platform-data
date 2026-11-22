# Đóng gói đủ nest host và các lớp cần thiết (Java 11+)

## 1. Vấn đề: chạy được trong IDE nhưng hỏng sau khi tạo JAR

Trong Java, một file nguồn có thể chứa lớp ngoài cùng và nhiều lớp lồng nhau. Chúng có vẻ là một khối mã nguồn, nhưng khi biên dịch, JVM thường nhận **nhiều tệp `.class`**. Từ **Java 11**, **nest-based access control** (JEP 181) cho phép những lớp thuộc cùng **nest** truy cập trực tiếp thành viên `private` của nhau. JVM xác nhận quyền truy cập bằng **metadata trong các class files**, không chỉ dựa vào tên có dấu `$`.

Nếu công cụ đóng JAR hoặc rút gọn ứng dụng loại mất một tệp `.class`, đặc biệt **nest host**, chương trình có thể khởi động được nhưng thất bại khi thực hiện private access. Đây là một lỗi đóng gói và class loading, không phải lý do nên thay `private` thành `public`.

Bài này hướng dẫn:

1. Xác định **nest host** và **nest members** ở mức JVM.
2. Hiểu tại sao phải đóng gói đủ class files, ngay cả khi host chỉ là “holder” không có method nghiệp vụ được gọi trực tiếp.
3. Biên dịch Java 11, tạo **JAR có đầy đủ host và members**, kiểm tra `NestHost`/`NestMembers` bằng `javap`.
4. Nhận diện hai loại artifact sai: **thiếu host** và **thiếu member**.
5. Thiết lập kiểm thử khi dùng class loader, Maven/Gradle, shading, shrinking hoặc multi-release JAR.

**Special Note:** chỉ dùng cơ chế Java 11+ vẫn còn áp dụng. Không dùng mẹo truy cập private, API nội bộ hoặc cách phát hành bytecode cũ làm giải pháp chính.

## 2. Nest-based access trong Java 11 hoạt động thế nào?

Một **nest** là tập hợp những lớp/giao diện có chung một **nest host**. JVM cho phép truy cập `private` giữa các **nestmates** khi xác minh membership hợp lệ.

Ví dụ trong package `lab.nest`:

~~~text
NestBox                      <-- host
├── NestBox$Reader           <-- member
└── NestBox$Vault            <-- member

Launch                       <-- entry point khác, không thuộc nest trên
~~~

Sau biên dịch:

| File bytecode | Thuộc tính chính | Ý nghĩa |
| --- | --- | --- |
| `NestBox.class` | `NestMembers` | Host liệt kê `NestBox$Reader` và `NestBox$Vault` |
| `NestBox$Reader.class` | `NestHost` | Reader khai báo `NestBox` là host |
| `NestBox$Vault.class` | `NestHost` | Vault khai báo cùng host |
| `Launch.class` | Không tự thành member chỉ vì cùng package | Chạy app và gọi public API của Reader |

Đây là cơ chế **class file version 55.0** (Java 11), được định nghĩa ở JVMS `4.7.28` (NestHost), `4.7.29` (NestMembers) và `5.4.4` (Access Control). Một host thông thường có `NestMembers`; từng member có `NestHost` trỏ về host. **Hai phía phải nhất quán** và thuộc cùng run-time package phù hợp.

### Tên giống nhau chưa đủ

Không thể suy ra nestmate chỉ vì hai tên file có cùng tiền tố `NestBox$`. JVM còn kiểm:

- Bytecode của member ghi đúng host.
- Host cho phép member đó trong `NestMembers`.
- Class và host thuộc **cùng run-time package** theo JVM.
- Class loader có thể phân giải đúng class identity và classfile không bị mâu thuẫn.
- Việc nạp/liên kết class và truy cập method/field thật sự thành công.

Cũng đừng nhầm `InnerClasses` và `NestHost`/`NestMembers`: thuộc tính `InnerClasses` hỗ trợ thông tin về các lớp lồng nhau, nhưng **không thay thế** metadata cho nest-based private access.

### Không phải một “nest object” ở Java source

Đây là một **quy tắc JVM**, không phải một class Java `Nest` mà ta tự khởi tạo. Khi viết nested Java classes theo cú pháp thông thường và biên dịch cho Java 11, `javac` sinh metadata tương ứng. Đối với ứng dụng bình thường, bạn **không cần tự ghi `NestMembers` vào bytecode**.

## 3. Tại sao host có thể bắt buộc dù không được gọi trực tiếp?

Một trường hợp đặc biệt được nêu trong **Oracle JDK 11 Release Notes**: một **top-level class hoặc interface** chỉ làm holder chứa nested classes, nên công cụ đóng gói có thể nghĩ rằng `Outer.class` “không sử dụng” và loại khỏi thư viện.

Nhưng hai nested classes có thể truy cập `private` của nhau. Khi liên kết những thao tác đó, JVM cần **đọc host** để xác minh membership. Nếu host không còn, JVM không thể xác nhận quyền truy cập dựa trên những classfiles đang có. **Một nest host không thể bị bỏ chỉ vì nó không có public method nghiệp vụ được gọi trực tiếp.**

~~~text
Trước khi đóng gói:                     JAR bị lọc sai:
  NestBox.class                           (thiếu NestBox.class)
  NestBox$Reader.class                    NestBox$Reader.class
  NestBox$Vault.class                     NestBox$Vault.class
  Launch.class                            Launch.class

  NestHost/NestMembers hợp lệ            Reader -> private Vault.prefix()
  JVM xác minh private access            JVM phải tìm NestBox để kiểm nest
                                        -> runtime linkage/access error
~~~

Trong Java 11+, **kết luận đúng không phải “mọi tên có dấu `$` đều tự động là nestmate”**, mà là **mọi class cần cho liên kết và kiểm tra nestmate phải được cung cấp đúng runtime**.

### “Đủ các lớp cần thiết” có phạm vi nào?

Tập class cần đóng gói gồm:

- **Host** có `NestMembers` tương ứng.
- **Members thực sự được sử dụng**, kể cả được gọi bởi các paths ít gặp, reflection hoặc framework.
- **Các dependencies** mà bytecode có thể nạp/tham chiếu, không chỉ những class ở trong nest.
- **Metadata nhất quán**, cùng bản build phù hợp, không lấy host của một phiên bản và member của phiên bản khác.
- **Package path và class loader phù hợp** với cách runtime tải classes.

Khi dùng `Class.getNestMembers()`, Java phải tải/kiểm tra danh sách members theo hợp đồng; class bị mất có thể làm `getNestMembers()` ném `LinkageError` dù luồng nghiệp vụ chưa gọi đến member đó. Vì vậy cách ít rủi ro nhất cho thư viện/application thông thường là **đóng gói toàn bộ output classfiles của module**, thay vì chọn thủ công vài class có vẻ cần ngay lúc start.

## 4. Ví dụ Java 11 đầy đủ: hai nestmates đọc private method và field

Ví dụ có **hai file source** và **bốn class files** sau biên dịch:

~~~text
src/
└── lab/
    └── nest/
        ├── NestBox.java
        └── Launch.java
~~~

### File `src/lab/nest/NestBox.java`

~~~java
package lab.nest;

public class NestBox {
    public static final class Vault {
        private static String prefix() {
            return "CODE";
        }
        private static int secret = 73;
    }
    public static final class Reader {
        public static String read() {
            return Vault.prefix() + "-" + Vault.secret;
        }
    }
}
~~~

`NestBox` là **host**. `Vault` và `Reader` là hai nested classes cùng nest. `Vault.prefix()` và `Vault.secret` đều là `private` nhưng `Reader.read()` có thể truy cập trực tiếp nhờ nest-based access.

**Vì sao `secret` không có `final`?** Một `private static final int` được gán hằng lúc compile có thể bị compiler inlined. Dùng `private static int` đảm bảo bytecode thực hiện `getstatic` để thấy rõ **truy cập private field qua nestmate**.

### File `src/lab/nest/Launch.java`

~~~java
package lab.nest;

import java.util.Arrays;
import java.util.stream.Collectors;

public class Launch {
    public static void main(String[] args) {
        System.out.println("value=" + NestBox.Reader.read());
        System.out.println("host=" + NestBox.Reader.class.getNestHost().getName());
        System.out.println("mates=" + NestBox.Vault.class.isNestmateOf(NestBox.Reader.class));
        String members = Arrays.stream(NestBox.class.getNestMembers())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
        System.out.println("members=" + members);
    }
}
~~~

`Launch` dùng các API public của `java.lang.Class` được bổ sung trong Java 11:

- `getNestHost()`: xác định nest host tại runtime.
- `isNestmateOf(other)`: xác định hai class thuộc cùng nest.
- `getNestMembers()`: liệt kê host và các members.

Ta sắp xếp tên bằng `sorted()` vì JDK **không bảo đảm thứ tự các members sau host** trong mảng trả về; nhờ đó stdout test ổn định.

**Hai file trên là một chương trình chạy được**, không phụ thuộc thư viện bên ngoài. Tên thư mục/package và tên file là bắt buộc vì chúng xác định binary names.

## 5. Biên dịch đúng target Java 11

Trong terminal Bash/Linux/macOS, ở thư mục có `src`:

~~~bash
mkdir -p out
javac --release 11 -d out \
  src/lab/nest/NestBox.java \
  src/lab/nest/Launch.java
~~~

Trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 11 -d out src/lab/nest/NestBox.java src/lab/nest/Launch.java
~~~

`--release 11` khiến `javac` dùng API, cú pháp và bytecode tương thích Java 11. `-d out` đặt kết quả biên dịch vào thư mục output theo package. Các classfiles phải là:

~~~text
out/
└── lab/
    └── nest/
        ├── Launch.class
        ├── NestBox.class
        ├── NestBox$Reader.class
        └── NestBox$Vault.class
~~~

Điều quan trọng: **một `NestBox.java` có thể sinh ra ba classfiles**, không phải chỉ `NestBox.class`. Nhân viên viết build script không được liệt kê “mỗi file source = một file .class” rồi loại các nested files.

### Test trực tiếp output classes

~~~bash
java -cp out lab.nest.Launch
~~~

Nếu lệnh trên chạy được nhưng `java -jar ...` không chạy được, nên kiểm tra **bước đóng JAR, classpath hoặc class loader** trước khi sửa code business.

### Clean build quan trọng

`javac -d out` không nhất thiết xóa các classfiles cũ còn sót từ những lần compile trước. Nếu refactor nested class hoặc chuyển package, **clean output directory trong build pipeline** trước khi tạo artifact; dùng lệnh clean tương ứng của build system. Không trộn host/member của những source versions khác nhau.

## 6. Tạo executable JAR chứa toàn bộ classes

Dùng JDK `jar`:

~~~bash
jar --create --file nest-app.jar --main-class lab.nest.Launch -C out .
java -jar nest-app.jar
~~~

`--main-class` đặt entry point trong manifest của JAR. `-C out .` yêu cầu đưa **toàn bộ nội dung `out`** vào archive, bảo toàn package path. Cách này không vô tình chỉ giữ `Launch.class` và các nested classes mà quên host.

**Stdout chính xác đã kiểm chứng** trên JDK 24 sau khi biên dịch `javac --release 11`:

~~~text
value=CODE-73
host=lab.nest.NestBox
mates=true
members=NestBox,Reader,Vault
~~~

Giải thích:

1. `value=CODE-73` cho biết `Reader` gọi trực tiếp `Vault.prefix()` và đọc `Vault.secret` (cả hai đều private) thành công.
2. `host=lab.nest.NestBox` xác nhận `Reader.getNestHost()` nhận đúng host.
3. `mates=true` cho biết `Vault` và `Reader` có cùng host được JVM công nhận.
4. `members=NestBox,Reader,Vault` là tên của host và hai members, đã được sort để tránh phụ thuộc thứ tự do runtime trả về.

### Kiểm tra nội dung JAR sau khi build

~~~bash
jar --list --file nest-app.jar
~~~

Các entries liên quan đã được thấy trong test:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/
lab/nest/
lab/nest/Launch.class
lab/nest/NestBox$Reader.class
lab/nest/NestBox$Vault.class
lab/nest/NestBox.class
~~~

**Không phụ thuộc thứ tự entries** trong một JAR khác. Khi viết CI assertion, kiểm tra bốn `.class` có tồn tại, không so sánh toàn bộ danh sách thành một chuỗi cứng.

Chỉ thấy `NestBox.class` trong `jar --list` cũng **chưa đủ**; nếu classfile đó lấy nhầm từ version khác thì metadata vẫn có thể mâu thuẫn với member đang phát hành.

## 7. Kiểm tra nest metadata thật bằng `javap -v`

`javap` đọc bytecode. Chạy:

~~~bash
javap -v -classpath nest-app.jar lab.nest.NestBox
javap -v -classpath nest-app.jar 'lab.nest.NestBox$Reader'
javap -v -classpath nest-app.jar 'lab.nest.NestBox$Vault'
~~~

Trong output rất dài, những phần đáng chú ý (đã rút gọn) là:

~~~text
NestBox.class:
    major version: 55
    NestMembers:
      lab/nest/NestBox$Reader
      lab/nest/NestBox$Vault

NestBox$Reader.class:
    major version: 55
    NestHost: class lab/nest/NestBox

NestBox$Vault.class:
    major version: 55
    NestHost: class lab/nest/NestBox
~~~

`NestHost` nằm ở member và chỉ hướng tới host; `NestMembers` ở host xác nhận những class được xem là member. **JVM xác minh quan hệ đó, không phải tên file tự quyết định quyền.**

Dấu nháy đơn quanh tên có `$` là quan trọng với Bash/PowerShell để shell không coi `$Reader` là tên biến. Nếu dùng Windows `cmd.exe`, cần quoting tương ứng với shell đó.

### Bytecode cho private access

~~~bash
javap -c -p -classpath nest-app.jar 'lab.nest.NestBox$Reader'
~~~

Trong bytecode của `read()`, test cho thấy các lệnh (đoạn rút gọn):

~~~text
invokestatic ... // Method lab/nest/NestBox$Vault.prefix:()Ljava/lang/String;
getstatic    ... // Field lab/nest/NestBox$Vault.secret:I
~~~

Đó là các thao tác trực tiếp tới **private method và field thuộc một class khác**. Compiler Java 11 không cần tạo cầu nối truy cập private theo cách của các compiler-target cũ. Chính vì thế **mối quan hệ nest phải còn nguyên vẹn khi chạy JAR**.

## 8. Phản ví dụ: JAR thiếu nest host

Tạo một artifact thử nghiệm cố tình chỉ chứa `Launch.class`, `NestBox$Reader.class`, `NestBox$Vault.class`, nhưng **không** có `NestBox.class`:

~~~bash
jar --create --file missing-host.jar --main-class lab.nest.Launch \
  -C out lab/nest/Launch.class \
  -C out 'lab/nest/NestBox$Reader.class' \
  -C out 'lab/nest/NestBox$Vault.class'

java -jar missing-host.jar
~~~

**Đây là phản ví dụ, tuyệt đối không phát hành artifact này.** Các class `Reader` và `Vault` có thể được tải, nhưng khi `Reader.read()` cần truy cập `Vault.prefix()` (private), JVM phải giải quyết nest host. Do `NestBox.class` không có, kiểm tra này thất bại.

**Kết quả kiểm chứng trên JDK 24:** `java` thoát với mã lỗi khác 0. Exception chính là `IllegalAccessError` khi Reader truy cập private method của Vault; thông báo còn chỉ ra lỗi **`NoClassDefFoundError: lab/nest/NestBox`** trong quá trình giải quyết host.

Thông báo bên dưới đã được rút gọn cho dễ đọc, **không phải stderr nguyên văn**:

~~~text
java.lang.IllegalAccessError: class lab.nest.NestBox$Reader
  tried to access private method lab.nest.NestBox$Vault.prefix()
...
Nest host resolution failed:
  java.lang.NoClassDefFoundError: lab/nest/NestBox
~~~

Đừng cố định một kiểu exception duy nhất cho mọi JDK/code path: lỗi class loading, nestmate validation hoặc private access có thể biểu hiện khác nhau. **Nguyên nhân cần sửa ở đây là thiếu classfile host**, không phải cú pháp `private` trong Java source.

## 9. Phản ví dụ: JAR có host nhưng thiếu member

Tạo artifact khác: có `NestBox.class` và `NestBox$Reader.class`, nhưng thiếu `NestBox$Vault.class`:

~~~bash
jar --create --file missing-vault.jar --main-class lab.nest.Launch \
  -C out lab/nest/Launch.class \
  -C out lab/nest/NestBox.class \
  -C out 'lab/nest/NestBox$Reader.class'

java -jar missing-vault.jar
~~~

**Trong lần kiểm chứng**, `Reader.read()` không tải được Vault nên có lỗi:

~~~text
java.lang.NoClassDefFoundError: lab/nest/NestBox$Vault
Caused by: java.lang.ClassNotFoundException: lab.nest.NestBox$Vault
~~~

Các dòng là phần có ý nghĩa của stderr, không phải toàn bộ output. Để tái hiện, hãy tạo hai source files ở phần 4 và biên dịch trước khi làm phản ví dụ. **Không chọn bản JAR lỗi làm đầu ra cần phát hành.**

### Tại sao lỗi có thể xuất hiện muộn?

Class loading/resolution có thể xảy ra khi một đường code được sử dụng. Nếu chương trình chưa gọi method cần `Vault`, việc `main` chạy qua một số bước không chứng minh toàn bộ JAR hợp lệ. Nhưng `Class.getNestMembers()` được thiết kế để lấy/kiểm tra các members do host ghi và có thể ném **`LinkageError`** khi member không có hoặc không hợp lệ.

Vì vậy test artifact nên gồm **cả chạy các thao tác private thật và kiểm `getNestMembers()`**. Không xem việc một lệnh `java -version` hoặc startup banner thành công là kiểm thử package đạt yêu cầu.

## 10. Class loader, package và module identity

Đối với JVM, run-time package không được quyết định chỉ bởi tên gói trong mã nguồn. Nó còn phụ thuộc vào **defining class loader**. Nếu hai class có cùng tên `lab.nest` nhưng được định nghĩa bởi hai loaders khác nhau, chúng có thể không thuộc cùng run-time package để kiểm nestmate access.

~~~text
AppClassLoader:
  lab.nest.NestBox
  lab.nest.NestBox$Vault

PluginClassLoader:
  lab.nest.NestBox$Reader
~~~

Đây là **sơ đồ tình huống rủi ro**, không phải cấu hình được khuyến nghị. Trong một hệ thống plugin hoặc custom class loader, có thể thiếu host ở loader định nghĩa member hoặc vô tình nạp những class names giống nhau nhưng identity khác. Khi đó `getNestHost()`/`isNestmateOf()` và thao tác private có thể không như mong đợi, thậm chí dẫn tới access/linkage error.

### Runtime package và module boundaries

- Giữ host/member dưới **binary names** đúng, thuộc cùng runtime package khi JVM thực hiện nest checks.
- Với JPMS, module location/readability/exports/opens còn ảnh hưởng cách truy cập qua modules. Nest-based access **không** là đường tắt cho caller bất kỳ vượt ranh giới module.
- Không nhân bản cùng class name trong nhiều JAR ở classpath rồi phụ thuộc tình cờ vào thứ tự resolution.
- Không trộn `NestBox.class` thuộc build A với `NestBox$Reader.class` thuộc build B.
- Không đổi `private` thành `public` để che lỗi class loader. Cần chẩn đoán identity và cách phân phối các file bytecode.

Khi debug, có thể kiểm:

~~~java
Class<?> reader = NestBox.Reader.class;
Class<?> vault = NestBox.Vault.class;

boolean sameNest = reader.isNestmateOf(vault);
Class<?> host = reader.getNestHost();
ClassLoader readerLoader = reader.getClassLoader();
ClassLoader hostLoader = host.getClassLoader();
~~~

**Mã minh họa trong package có `NestBox`**, không phải chương trình độc lập. Các `Class<?>` khác nhau không trở thành cùng loại chỉ vì `getName()` giống nhau. `ClassLoader` của class thuộc bootstrap loader có thể là `null`, điều đó tự nó không phải lỗi.

## 11. Build tools, shading và shrinkers

### Maven / Gradle

Các plugin JAR thông thường lấy toàn bộ `.class` từ thư mục output. Tuy nhiên, cấu hình exclude/filter/assembly riêng có thể loại bớt classes. Khi build Java 11:

1. Clean build output, tránh stale bytecode.
2. Compile với `--release 11` (hoặc source/target hợp lệ theo requirement).
3. Kiểm output directory **có host và nested member files**.
4. Kiểm **JAR cuối cùng**, không chỉ output của IDE.
5. Thực sự chạy chính artifact sẽ đưa lên môi trường triển khai.

**Không viết exclude pattern kiểu “bỏ tất cả `*$*.class`”**: ký tự `$` thường xuất hiện trong tên nested, local hoặc anonymous classes. Không chỉ tìm những class Java public ở gốc package rồi quyết định JAR đã đủ.

### Fat JAR, shadow, relocate và obfuscation

Các công cụ shading có thể đổi package hoặc binary names. Một phép đổi tên **file entry ZIP** mà không sửa đồng bộ **constant pool, `NestHost` và `NestMembers`** là không đúng.

Ví dụ thay:

~~~text
lab/nest/NestBox$Reader.class
       thành
relocated/nest/NestBox$Reader.class
~~~

nhưng vẫn giữ `NestHost: lab/nest/NestBox` trong bytecode mới sẽ khiến quan hệ nest không tương ứng với lớp đã di chuyển.

**Cách đúng:** dùng transformer/shrinker hỗ trợ Java 11 nest metadata, cấu hình keep rules và relocation nhất quán, rồi kiểm artifact **sau biến đổi** bằng `javap -v` và smoke test private access. Nếu build tool loại host vì không thấy reference trực tiếp, phải điều chỉnh keep rules phù hợp với metadata và các đường reflective loading.

### Thin JAR và dependency ngoài

Không nhất thiết **tất cả** dependency của chương trình phải đóng trong một JAR. Một thin JAR có thể chạy với classpath/module path đầy đủ. Nhưng đối với **các members trong một nest**, tránh chia host/member qua các loaders độc lập, tránh missing artifact và giữ classfile metadata/version tương ứng. Khi lệnh `java -jar` được dùng, đừng giả định mọi dependency nằm đâu đó trong thư mục đều tự được đưa vào classpath; phải thiết lập manifest/module/runtime launcher phù hợp.

### Multi-release JAR

Một multi-release JAR có thể có những biến thể class cho các JDK khác nhau. Với classfiles thuộc nest, cần bảo toàn host và members **trong mỗi runtime view được chọn** và không ghép classfile phiên bản này với metadata phiên bản khác. Hãy test trên JDK 11 và các JDK triển khai đã xác định.

## 12. Kiểm thử CI: không dừng ở “có file JAR”

| Bài kiểm tra | Công cụ | Điều cần đạt |
| --- | --- | --- |
| Compiler target | `javac --release 11` | Không dùng API/classfile mới ngoài Java 11 |
| Classfile version | `javap -v` | `major version: 55` với output Java 11 |
| Host hiện diện | `jar --list --file ...` | Có `NestBox.class` |
| Members hiện diện | `jar --list --file ...` | Có `NestBox$Reader.class` và `NestBox$Vault.class` |
| Nest metadata | `javap -v` | Host có `NestMembers`; members có `NestHost` đúng |
| Runtime membership | `getNestHost()`, `isNestmateOf()` | Host đúng, mates là true |
| Reflective membership | `getNestMembers()` | Nạp/kiểm danh sách không có linkage error |
| Private access thực tế | `java -jar nest-app.jar` | `value=CODE-73`, exit code 0 |
| Negative test thiếu host | `java -jar missing-host.jar` | Phát hiện access/linkage failure |
| Negative test thiếu member | `java -jar missing-vault.jar` | Phát hiện missing class |
| Build sau shading/shrinking | Lặp các test trên JAR cuối | Metadata và class inventory còn phù hợp |
| Runtime classloader thật | Integration test cùng launcher/plugin framework | Không nhầm loader và runtime package |

**`jdeps` có ích** để phân tích phụ thuộc class/module, nhưng không tự chứng minh quan hệ nestmate và mọi khả năng tải class bằng reflection. Cần phối hợp **kiểm tĩnh file/attributes + runtime tests**.

Khi automation cần kiểm source/classfile, dùng đường dẫn đúng của artifact vừa build; không vô tình kiểm một file `nest-app.jar` cũ. Với CI, có thể lấy sha256 của artifact cuối rồi sử dụng cùng tệp đó cho test và deploy.

## 13. Phân biệt các lỗi dễ gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và khắc phục |
| --- | --- | --- |
| `NoClassDefFoundError: NestBox$Vault` | Thiếu member trực tiếp dùng | Kiểm JAR entries và classpath |
| `ClassNotFoundException` khi `Class.forName` | Loader không tìm tên binary được yêu cầu | Kiểm package path / loader / artifact |
| `IllegalAccessError` khi Reader gọi private Vault | Nest validation thất bại, có thể thiếu host hoặc metadata lệch | Kiểm host `NestMembers`, member `NestHost` và runtime loader |
| `NoClassDefFoundError: NestBox` trong nguyên nhân lỗi host | Host bị loại hoặc không tải được | Phục hồi host đúng build |
| `LinkageError` từ `getNestMembers()` | Một nest member không thể tải/xác minh | Giữ đủ members, kiểm biến đổi bytecode |
| `isNestmateOf` trả false | Hai class không chia cùng host hợp lệ | Dùng `getNestHost` và `javap` đối chiếu |
| `getNestHost()` trả chính member | Host không xác minh được, hoặc class là singleton nest | Kiểm metadata và source gốc |
| `UnsupportedClassVersionError` | JDK chạy cũ hơn classfile target | Triển khai Java 11+ phù hợp |
| IDE chạy nhưng JAR lỗi | JAR thiếu host/member, shadow trùng class, launcher khác | Kiểm artifact sau đóng gói |
| Lỗi chỉ ở môi trường plugin | Class loader/runtime package khác nhau | Kiểm loaders và cách chia modules |
| Runtime báo private access lỗi sau obfuscate | Metadata hoặc references bị rewrite không nhất quán | Sửa transformer và test lại final artifact |

**Không sửa bằng cách thay visibility trong source**, thêm reflection bypass hoặc thay đổi bảo mật JVM. Những giải pháp đó làm mất ý nghĩa encapsulation, che giấu lỗi phát hành và có thể hỏng thêm ở các runtime mới.

## 14. Checklist phát hành một thư viện dùng nest-based access

1. [ ] Xác định rõ **host** và mọi **member** qua compiler output và `javap`.
2. [ ] Đóng đầy đủ class files liên quan, kể cả host chỉ đóng vai trò holder.
3. [ ] Không exclude file chứa `$` hoặc xóa host chỉ vì “không gọi trực tiếp”.
4. [ ] Dùng clean build, tránh stale class files và trộn versions.
5. [ ] Giữ đúng package directory, binary name và class loader.
6. [ ] Kiểm `NestMembers` và `NestHost` còn khớp sau packaging/obfuscation.
7. [ ] Dùng `--release 11` khi module yêu cầu Java 11; kiểm major version 55.
8. [ ] Không phụ thuộc ngẫu nhiên vào classpath ordering/duplicate classes.
9. [ ] Nếu dùng shading, transformer phải hỗ trợ nest metadata.
10. [ ] Nếu dùng class loaders hoặc modules, test trong môi trường triển khai tương đương.
11. [ ] Kiểm JAR bằng `jar --list` và `javap -v`.
12. [ ] Chạy `java -jar`/entry point thực trên final artifact; kiểm exit code.
13. [ ] Gọi `getNestHost()`, `getNestMembers()`, `isNestmateOf()` và private access thật trong QA.
14. [ ] Có test âm thiếu host/member để chắc chắn pipeline phát hiện lỗi trước release.
15. [ ] Không thay `private` thành `public` hoặc sử dụng tricks legacy để che lỗi đóng gói.

**Kết luận:** Java 11 nest-based access cho phép các lớp cùng nest truy cập trực tiếp `private`, nhưng cơ chế này phụ thuộc **đúng class files, metadata và runtime identity**. **Nest host phải đi kèm các members cần thiết**, ngay cả khi host không có business method được gọi. Hãy kiểm tra **JAR thực tế**, không chỉ source hoặc output IDE.

## Tài liệu chính thức vẫn còn áp dụng

- [OpenJDK JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): cơ chế nestmate của Java 11.
- [Oracle JDK 11 Release Notes — JEP 181 và packaging](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): yêu cầu giữ top-level host khi members truy cập private.
- [Java SE 11 JVMS `4.7.28 — NestHost](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28): metadata ở member.
- [Java SE 11 JVMS `4.7.29 — NestMembers](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29): metadata ở host.
- [Java SE 11 JVMS `5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4): kiểm tra private nestmate access.
- [Oracle Java SE 11 — `Class`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html): `getNestHost()`, `getNestMembers()`, `isNestmateOf()`.
- [Oracle Java SE 25 — `Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): API vẫn được hỗ trợ.
- [Oracle Java SE 25 — jar tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): `--create`, `--file`, `--list`, `-C`, `--main-class`.
- [Oracle Java SE 25 — javap tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): `-v`, `-p`, `-c`.

Bài chỉ dùng cơ chế chuẩn **Java 11+ hiện còn áp dụng**. Các kết quả thực thi và lỗi minh họa được kiểm bằng classfiles Java 11 trên JDK 24, không suy đoán rằng thông báo exception phải giống nhau trên mọi môi trường.