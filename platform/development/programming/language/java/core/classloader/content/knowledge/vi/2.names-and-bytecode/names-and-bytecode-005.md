# Phiên bản major, minor và giới hạn JDK hỗ trợ bytecode

## 1. Vì sao phiên bản bytecode quan trọng?

Khi biên dịch Java, `javac` chuyển mã nguồn thành **class file** (thường có đuôi `.class`). JVM/ClassLoader đọc định dạng nhị phân của class file để nạp, kiểm tra và sử dụng lớp. Mỗi class file tự khai báo **phiên bản định dạng** dưới dạng `major.minor`; đây là thông tin để JVM quyết định nó có hiểu class file đó hay không.

Cần tách biệt ba khái niệm:

- **Phiên bản JDK dùng để biên dịch:** phiên bản công cụ `javac` đang chạy, chẳng hạn JDK 21.
- **Phiên bản class file:** cặp số `major_version` và `minor_version` thực sự ghi trong từng `.class`, chẳng hạn `61.0` (Java 17).
- **Phiên bản JVM/JRE chạy chương trình:** môi trường phải nạp class file, chẳng hạn Java 17 hoặc Java 21.

Ví dụ, dùng `javac` của **JDK 21** với `--release 17` thường tạo class file **61.0**, có thể được JVM Java 17 nạp nếu các class và thư viện khác cũng tương thích. Nếu biên dịch mặc định trên JDK 21, class file thông thường có phiên bản **65.0** và JVM Java 17 không hiểu nó.

**Quy tắc cốt lõi:** JVM phải hỗ trợ phiên bản *của từng class file được nạp*, không chỉ phiên bản JDK trên máy lập trình. ClassLoader tùy chỉnh không tự làm JVM hiểu định dạng mới hơn.

## 2. Vị trí major và minor trong cấu trúc `.class`

Đầu mỗi class file chuẩn có cấu trúc:

```text
Offset (byte)    Kích thước     Trường           Ví dụ cho class Java 17
0                4 byte         magic            CA FE BA BE
4                2 byte         minor_version    00 00  (= 0)
6                2 byte         major_version    00 3D  (= 61)
8                2 byte         constant_pool_count
...              ...            các cấu trúc còn lại
```

Theo Java Virtual Machine Specification (JVMS), các số `u2` là **số nguyên không dấu 16-bit** và được ghi theo thứ tự **big-endian**. Vì thế 8 byte mở đầu `CA FE BA BE 00 00 00 3D` tương ứng magic hợp lệ, minor 0 và major 61. Trường `minor_version` đứng **trước** `major_version`, dù khi nói phiên bản ta viết **61.0** (major trước minor).

- `magic` xác nhận dấu hiệu class file Java; có magic đúng vẫn chưa đảm bảo phần còn lại hợp lệ.
- `major` xác định thế hệ định dạng class file JVM cần hỗ trợ.
- `minor` bổ sung quy tắc tương thích, đặc biệt có ý nghĩa với **preview features** từ Java 12.
- Bytecode instruction, constant pool, attribute và các cấu trúc mới có thể đòi hỏi JVM của phiên bản Java tương ứng. Không thể chỉ sửa 2 byte major để biến một class mới thành class cũ hợp lệ.

## 3. Bảng quy đổi Java ↔ major version

Bảng dưới đây cho biết **major được giới thiệu** ở mỗi phiên bản Java; phiên bản Java cũ 1.x dùng cách đặt tên khác từ Java 5 trở đi.

| Java/JDK | Major | Java/JDK | Major | Java/JDK | Major |
|---|---:|---|---:|---|---:|
| JDK 1.0.2, 1.1 | 45 | Java 9 | 53 | Java 18 | 62 |
| JDK 1.2 | 46 | Java 10 | 54 | Java 19 | 63 |
| JDK 1.3 | 47 | Java 11 | 55 | Java 20 | 64 |
| JDK 1.4 | 48 | Java 12 | 56 | Java 21 | 65 |
| Java 5 | 49 | Java 13 | 57 | Java 22 | 66 |
| Java 6 | 50 | Java 14 | 58 | Java 23 | 67 |
| Java 7 | 51 | Java 15 | 59 | Java 24 | 68 |
| Java 8 | 52 | Java 16 | 60 | Java 25 | 69 |
| Java 17 | 61 | Java 26 | 70 | — | — |

Đối với **Java 5 trở lên**, có thể ghi nhớ công thức:

```text
major = số phiên bản Java + 44
Java 8  → 52
Java 17 → 61
Java 21 → 65
Java 26 → 70
```

Công thức này không áp dụng máy móc cho các tên phiên bản lịch sử `1.0`–`1.4`: chẳng hạn cả JDK 1.0.2 và 1.1 gắn với major 45. Đây cũng không phải cách tính minor.

Tính đến Java SE 26, JVMS quy định JVM phù hợp Java SE 26 hỗ trợ **major 45 đến 70**. Mỗi phiên bản JVM có giới hạn tối đa của chính nó: Java 8 là 52, Java 11 là 55, Java 17 là 61, Java 21 là 65, Java 25 là 69, Java 26 là 70. Các bản JVM chuẩn cũng hỗ trợ nhiều major cũ (theo bảng hỗ trợ của JVMS), nhưng khả năng *nạp được class file* không bảo đảm mọi thư viện/API cũ hoặc mọi hành vi chương trình còn tương thích.

## 4. Minor version và preview bytecode

### 4.1. Class file thông thường

Trong các bản Java hiện đại, class file biên dịch không phụ thuộc preview thường có `minor=0`, ví dụ `52.0`, `61.0`, `65.0`. Tuy nhiên, không nên khẳng định rằng **mọi** class file Java trong lịch sử đều có minor 0:

- Với major **45–55** (đến Java 11), JVMS cho phép minor từ 0 đến 65535. Lịch sử JDK 1.0.2 hỗ trợ `45.0`–`45.3`; các phiên bản đầu có quy tắc tương thích riêng.
- Với major **56 trở lên** (từ Java 12), minor **chỉ được là 0 hoặc 65535**. Một minor khác, chẳng hạn `61.1`, không hợp lệ theo quy tắc này.

### 4.2. Giá trị 65535 (0xFFFF) dành cho preview

Từ Java 12, class file có `major=M` (M ≥ 56) và `minor=65535` biểu thị rằng nó **phụ thuộc các preview features của đúng bản Java gắn với M**. Ví dụ:

- `61.65535` gắn với preview của **Java 17**.
- `65.65535` gắn với preview của **Java 21**.
- `70.65535` gắn với preview của **Java 26**.

Để nạp class file preview, JVM phải **đúng phiên bản Java đó** và preview phải được bật ở runtime (`--enable-preview`). JVM Java 21 không được nạp `61.65535` của Java 17, **kể cả khi bật** `--enable-preview`. JVM Java 17 cũng không được nạp `65.65535`. Đây là khác biệt lớn so với `61.0` thông thường, vốn có thể chạy trên JVM mới hơn khi các điều kiện khác đáp ứng.

Lệnh mẫu khi biên dịch **mã thực sự dùng preview feature mà JDK 21 cung cấp** (tệp và cú pháp phải phù hợp Java 21):

```bash
javac --enable-preview --release 21 PreviewDemo.java
java --enable-preview PreviewDemo
```

Khi muốn dùng `--release 21`, bản `javac` phải hỗ trợ target đó. Đây là ví dụ cách gọi lệnh, chưa phải chương trình chạy độc lập vì nội dung `PreviewDemo.java` phụ thuộc preview feature bạn chọn. Không phải mọi lần thêm `--enable-preview` đều có nghĩa mọi class trong kết quả đều có minor 65535: cần kiểm tra class file thực tế.

**Cảnh báo tương thích:** Preview API và preview language feature có thể thay đổi hoặc bị loại khỏi phiên bản Java sau. Không dùng quy tắc "JVM mới hơn chạy mọi class cũ" cho class file preview.

## 5. Kiểm tra major/minor bằng công cụ JDK

### 5.1. Dùng `javap -verbose`

Tạo tệp `VersionDemo.java`:

```java
public final class VersionDemo {
    public static void main(String[] args) {
        System.out.println("Bytecode target demo");
    }
}
```

Trên **JDK 17 hoặc mới hơn** có hỗ trợ `--release 17`, chạy:

```bash
javac --release 17 VersionDemo.java
javap -verbose VersionDemo
java VersionDemo
```

Trong phần đầu kết quả `javap -verbose`, hãy tìm hai dòng:

```text
  minor version: 0
  major version: 61
```

Đây là **trích đoạn** của kết quả `javap`; phần constant pool và các metadata khác đã lược bỏ. Chương trình Java cho stdout đúng một dòng:

```text
Bytecode target demo
```

Có thể dùng `javap -verbose -classpath out ten.goipackage.VersionDemo` khi `.class` nằm trong thư mục `out` và có `package`. `javap` đọc class file để xem metadata; nó không phải cách xác minh toàn bộ runtime dependency đều tương thích.

### 5.2. Đọc trực tiếp 8 byte đầu bằng Java 17+

Một chương trình nhỏ cho thấy major/minor thực sự nằm trong file, không cần dựa vào tên JDK:

Tạo `ClassVersionReader.java`:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassVersionReader {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClassVersionReader <file.class>");
        }

        try (DataInputStream in =
                     new DataInputStream(Files.newInputStream(Path.of(args[0])))) {
            int magic = in.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IOException("Not a Java class file");
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            System.out.printf("major=%d, minor=%d%n", major, minor);
        }
    }
}
```

Trong cùng thư mục với `VersionDemo.class` của mục 5.1, chạy:

```bash
javac --release 17 ClassVersionReader.java
java ClassVersionReader VersionDemo.class
```

Stdout chính xác khi `VersionDemo.class` được tạo bằng lệnh `javac --release 17` ở trên và không dùng preview:

```text
major=61, minor=0
```

`DataInputStream.readInt()` đọc magic dạng 4 byte, `readUnsignedShort()` đọc từng `u2` big-endian thành số nguyên 0–65535. Chương trình trên chỉ đọc **header**, không kiểm tra tính hợp lệ của constant pool, method, verifier hay khả năng chạy của class.

### 5.3. Đọc lỗi và xác nhận công cụ đang dùng

Kiểm tra cả compiler và JVM trên môi trường thực tế:

```bash
javac -version
java -version
```

Hai lệnh có thể trỏ đến **hai bản JDK/JRE khác nhau**, đặc biệt trong IDE, CI/CD, Docker, IDE Gradle daemon hay cấu hình `PATH`. Thấy compiler là JDK 21 **không có nghĩa** bytecode chắc chắn là major 65: hãy kiểm tra `--release` và `javap`. Tương tự, chọn Java 17 trong IDE chưa chắc mọi tác vụ build hoặc launcher đang chạy JVM 17.

## 6. JDK hỗ trợ bytecode đến đâu?

Quy tắc đơn giản cho class file **không preview**: JVM Java N chỉ nạp được class file có major nằm trong tập hỗ trợ của N. Nhìn vào **major** để xét giới hạn định dạng, sau đó phải xét thêm **minor**, cấu trúc file, các thư viện và API lúc chạy.

| Class file | JVM Java 8 | JVM Java 17 | JVM Java 21 | JVM Java 26 |
|---|---|---|---|---|
| `52.0` (Java 8) | Hỗ trợ | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| `61.0` (Java 17) | Không | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| `65.0` (Java 21) | Không | Không | Hỗ trợ | Hỗ trợ |
| `70.0` (Java 26) | Không | Không | Không | Hỗ trợ |
| `61.65535` (preview Java 17) | Không | Chỉ khi bật preview | Không | Không |

"Hỗ trợ" trong bảng là **hỗ trợ phiên bản class file** theo JVM chuẩn; không phải lời hứa ứng dụng chạy thành công. Ví dụ, một class 52.0 gọi thư viện không hiện diện lúc chạy vẫn có thể gặp `ClassNotFoundException`, `NoClassDefFoundError` hay `NoSuchMethodError`. Cấu trúc file bị lỗi cũng có thể dẫn đến `ClassFormatError` hoặc lỗi verification.

Một JVM **không tự chuyển ngược** định dạng mới thành cũ. Khi cùng quá trình chạy có 100 class file, chỉ cần một class được nạp có major vượt mức JVM hỗ trợ là ứng dụng có thể lỗi ở thời điểm nạp class đó; một số lỗi vì thế không xuất hiện ngay lúc khởi động.

## 7. Tạo bytecode phù hợp JVM đích

### 7.1. Ưu tiên `--release`

Nếu triển khai trên Java 17 nhưng máy build dùng JDK 21, nên chọn:

```bash
javac --release 17 VersionDemo.java
```

`--release 17` phối hợp **ngôn ngữ nguồn**, **target class file** và **API chuẩn được expose cho Java 17**. Nó giúp tránh tình huống code sinh major 61 nhưng gọi nhầm API chuẩn chỉ có từ Java 21. Điều này vẫn không thay thế việc kiểm tra tương thích các thư viện bên thứ ba và chạy test thực tế trên Java 17.

Ví dụ với JDK 21:

```bash
javac VersionDemo.java
```

Nếu không có cấu hình target khác, class thường là **65.0**. Còn:

```bash
javac --release 17 VersionDemo.java
```

tạo **61.0**. Bạn có thể đối chiếu bằng `javap -verbose`.

### 7.2. Phân biệt `--source`, `--target`, `--release`

- `--source 17`: áp dụng mức cú pháp/ngôn ngữ Java 17 khi biên dịch.
- `--target 17`: yêu cầu phiên bản class file đích tương ứng Java 17.
- `--release 17`: đồng bộ source, target và tập API nền tảng Java 17 mà compiler cho phép sử dụng; thường là lựa chọn an toàn nhất cho cross-compilation.

**Chỉ** đặt `--target 17` không chứng minh ứng dụng sẽ chạy trên Java 17: mã có thể tham chiếu API chuẩn xuất hiện ở bản Java mới hơn nếu không khống chế API lúc compile; thư viện phụ thuộc cũng có thể có class version cao hơn. `--release` không tự biên dịch lại thư viện đã đóng gói hoặc sửa lỗi tương thích hành vi giữa hai JVM.

Với Maven/Gradle, cấu hình compiler release tương đương cần áp dụng cho module build thích hợp; sau build hãy xác nhận artifact `.class` thật, đồng thời chạy integration test bằng **JVM thấp nhất được hỗ trợ**.

## 8. Khi ClassLoader nạp bytecode không tương thích

Quá trình nạp class có thể nhìn khái quát:

```text
ClassLoader được yêu cầu nạp tên lớp
    ↓
Tìm / lấy bytes của class file
    ↓
JVM đọc header (magic, minor, major) và cấu trúc class
    ↓
Kiểm tra định dạng và giới hạn JVM
    ├─ Không hỗ trợ phiên bản → UnsupportedClassVersionError
    ├─ Cấu trúc không hợp lệ → ClassFormatError / lỗi liên quan
    └─ Hợp lệ → tạo lớp; liên kết, verification và khởi tạo theo thời điểm tương ứng
```

Đây là sơ đồ *khái niệm*; trình tự và thời điểm load/link/verify/init cụ thể phụ thuộc tình huống. Một custom ClassLoader có thể đọc bytes từ tệp, mạng, JAR hoặc dữ liệu sinh động và gọi `defineClass(...)`, nhưng cuối cùng JVM vẫn kiểm tra định dạng theo giới hạn phiên bản hiện hành.

**Ví dụ lỗi:** class biên dịch bằng JDK 21 theo mặc định (major 65), chạy trên JVM Java 17 (tối đa major 61) sẽ không nạp được. Thông báo thường nhắc `UnsupportedClassVersionError`, `class file version 65.0` và JVM chỉ nhận đến `61.0`; lời văn chính xác khác giữa phiên bản hoặc nhà cung cấp JVM. Cách xử lý là **chạy trên JVM phù hợp** hoặc **biên dịch lại class và mọi dependency liên quan cho Java 17**, nếu mã/API cho phép. Không sửa thủ công header để "hạ version".

Phân biệt nhanh các họ lỗi thường nhầm:

| Hiện tượng | Điểm cần kiểm tra |
|---|---|
| `UnsupportedClassVersionError` | Major/minor của `.class` so với giới hạn JVM; preview có đúng Java release và được bật không |
| `ClassFormatError` | Dữ liệu class file lỗi cấu trúc hoặc không đúng định dạng; `UnsupportedClassVersionError` là một dạng cụ thể trong họ này |
| `VerifyError` | Bytecode vi phạm quy tắc verifier; không nhất thiết do class file quá mới |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu lớp trên classpath/module path, lỗi khi liên kết/nạp hoặc lỗi trước đó; không quy ngay cho version |
| `NoSuchMethodError` | Lệch phiên bản API/thư viện ở runtime dù major của class có thể hợp lệ |

### Tình huống thực tế: Java 17 service dùng thư viện Java 21

Giả sử service được compile `--release 17`, nhưng một dependency JAR chứa `SomeLibrary.class` có major 65. Build *có thể* không thể dùng dependency đó tùy cách biên dịch; nếu artifact vẫn được đóng gói và JVM Java 17 phải nạp class 65.0, runtime sẽ lỗi version. Kiểm tra các class bên trong JAR hoặc dùng công cụ dependency analysis/build compatibility; chỉ kiểm tra entry-point class là chưa đủ.

Một **Multi-Release JAR** có thể mang class khác nhau trong `META-INF/versions/<N>/` và chọn biến thể thích hợp theo JVM đang chạy khi JAR được cấu hình multi-release đúng cách. Điều này giúp thư viện cung cấp nhiều mức tương thích, nhưng không làm một JVM cũ tự hiểu phiên bản class file mới.

## 9. Quy trình chẩn đoán khi gặp lỗi bytecode version

1. Ghi nhận **JVM thực tế** của process lỗi (terminal, service, test runner, Docker/CI); chạy `java -version` đúng môi trường.
2. Tìm **tên class bị lỗi** trong stack trace; xác định class đó nằm trong module của bạn hay JAR phụ thuộc.
3. Xem `major/minor` của **chính class file đó** bằng `javap -verbose` hoặc chương trình đọc header; không suy luận chỉ từ `pom.xml`/Gradle target.
4. So phiên bản class với giới hạn JVM và kiểm tra `minor=65535` cho preview.
5. Nếu class quá mới, nâng runtime theo yêu cầu hệ thống hoặc build/publish artifact theo target phù hợp; kiểm tra cả dependency transitives.
6. Kiểm tra khả năng dùng API trên runtime thấp nhất và chạy smoke/integration tests trên đúng JVM deploy.

**Lỗi phổ biến cần tránh:** nhầm version JDK với version bytecode; cho rằng minor không quan trọng; nghĩ `major thấp` bảo đảm chạy được mọi API; tin rằng bật `--enable-preview` ở JVM mới sẽ chạy class preview của JVM cũ; sửa hex của major thay cho biên dịch lại; chỉ nâng JDK build mà quên JVM production.

## 10. Câu hỏi tự kiểm tra

1. 8 byte đầu `CA FE BA BE 00 00 00 41` chỉ ra phiên bản nào? **Đáp án:** major `0x41=65`, minor 0, tức class file Java 21 thông thường.
2. JVM Java 17 có nạp được class `65.0` không? **Không**; Java 17 hỗ trợ tối đa major 61.
3. JVM Java 21 với `--enable-preview` có chạy được class `61.65535` không? **Không**; preview class Java 17 chỉ được nạp trên Java 17 khi preview được bật.
4. JDK 21 có tạo được class `61.0` không? **Có**, chẳng hạn với `javac --release 17` cho mã phù hợp.
5. Class `61.0` chạy được trên JVM Java 21 có chứng minh app chắc chắn hoạt động không? **Không**; còn phải đáp ứng dependency, API, liên kết và hành vi runtime.
6. Tại sao `minor=1` của class `61.1` là bất hợp lệ? **Vì** với major từ 56 trở lên, minor chỉ được phép 0 hoặc 65535.

## Tài liệu chuẩn để tra cứu

- [Java Virtual Machine Specification, Java SE 26 — §4.1: The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html): định dạng header, bảng major, tập hỗ trợ và quy tắc minor/preview.
- [JVMS Java SE 26 — §1.5: Preview Features](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-1.html): điều kiện bật và sự ràng buộc phiên bản preview.
- [Java `javac` tool reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): ý nghĩa `--release`, `--source`, `--target`.
- [Java `javap` tool reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): cách xem chi tiết class file.

Một class file **thông thường** được thiết kế để JVM cùng phiên bản hoặc phiên bản mới hơn hỗ trợ; một class file **preview** bị ràng buộc vào đúng release. Trong cả hai trường hợp, phiên bản class file chỉ là **điều kiện cần** của khả năng nạp và chạy mã Java.
