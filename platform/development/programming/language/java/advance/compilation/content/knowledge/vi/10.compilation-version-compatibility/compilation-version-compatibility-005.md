# Đọc major, minor version và lỗi UnsupportedClassVersionError trong Java

Một tệp `.class` là bytecode theo định dạng Java Virtual Machine (JVM), có **phiên bản class file** riêng. Khi `javac` tạo bytecode bằng một mức ngôn ngữ/đích biên dịch, class file có số **major version** và **minor version** trong header. JVM cần hỗ trợ định dạng class file đó để có thể tải và liên kết lớp.

Nếu một runtime cũ nhận một class được tạo cho phiên bản Java mới hơn, nó có thể ném **`java.lang.UnsupportedClassVersionError`**. Lỗi này liên quan đến khả năng đọc **định dạng bytecode**; nó khác với lỗi thiếu method/API, khác với lỗi cú pháp lúc biên dịch, và cũng không đồng nghĩa với việc “phiên bản thư viện Maven/Gradle quá mới” theo số version của artifact.

Bài này trình bày cách đọc số major/minor, xác định Java release tương ứng, dùng `javap` hoặc một chương trình Java độc lập để đọc header, hiểu preview class files, chẩn đoán lỗi, và chọn cấu hình biên dịch bảo đảm ứng dụng chạy được trên JDK/JRE mục tiêu.

## 1. Java source, javac, class file và JVM là bốn lớp thông tin

Ví dụ một dự án có:

~~~text
HelloVersion.java   -- javac -->   HelloVersion.class   -- JVM -->   thực thi
      |                               |                       |
  mã nguồn Java                   bytecode                runtime Java
  cú pháp/API cần hỗ trợ          major/minor             giới hạn version
~~~

Các thông tin dễ bị nhầm:

| Thông tin | Nó nói về điều gì? | Cách kiểm tra |
| --- | --- | --- |
| Source language level | Cú pháp/ngữ nghĩa mà compiler chấp nhận, ví dụ Java 17 | `javac --release 17` hoặc cấu hình build |
| Compiler version | Bản `javac` thực sự đang chạy | `javac -version` |
| Class file major/minor | Định dạng bytecode được tạo ra | `javap -verbose` hoặc đọc 8 byte đầu |
| Runtime version | JVM được lệnh `java` thực sự khởi động | `java -version` |
| Thư viện/API runtime | Những class và method có thật trên runtime classpath/module path | JDK API và dependency thực tế |

**JDK 21 có thể tạo class file cho Java 17** khi cấu hình hợp lệ bằng `--release 17`. Vì thế không thể suy ra số major chỉ từ `javac -version`. Ngược lại, việc một class có major tương thích không chứng minh mọi dependency và API mà chương trình sử dụng cũng tương thích runtime.

## 2. Header class file: magic, minor và major

Theo cấu trúc class file, các trường đầu tiên là:

~~~text
Offset (byte)   Độ dài   Trường
0–3             4        magic          = 0xCAFEBABE
4–5             2        minor_version
6–7             2        major_version
8...                     constant_pool_count, constant pool, ...
~~~

Cả hai trường version đều là **unsigned 16-bit** và được lưu theo thứ tự **big-endian** (byte cao trước). Bốn byte magic `CA FE BA BE` dùng để nhận biết định dạng class file.

Ví dụ một file Java 17 thông thường bắt đầu bằng:

~~~text
CA FE BA BE 00 00 00 3D ...
| magic     |minor|major|
             0x0000 0x003D
                     0x3D = 61
~~~

Nghĩa là:

- `major_version = 61`: class file tương ứng Java 17.
- `minor_version = 0`: giá trị thông thường của file class được compiler Java 17 tạo không sử dụng preview feature.
- `0xCAFEBABE`: magic number; nó **không phải** số phiên bản.
- Bytecode sau header còn có constant pool, thông tin class, field, method, attributes... Việc đọc đúng 8 byte đầu chỉ xác định header, **chưa kiểm chứng toàn bộ file**.

Một ví dụ khác:

~~~text
CA FE BA BE 00 00 00 34
~~~

`0x34` ở hai byte major là 52 hệ thập phân, tức mức class file của Java 8. Không đọc nhầm `00 34` thành 34 hệ thập phân.

**Major và minor là hai trường độc lập**, không phải cách viết version dạng số thực. Ví dụ `61.0` có nghĩa major = 61, minor = 0; `61.65535` là major = 61, minor = 65535, **không** phải Java 61 bản vá 65535.

## 3. Bảng đối chiếu major version với Java release

| Java release | Major | Minor thông thường |
| --- | ---: | ---: |
| Java 1.1 | 45 | 3 |
| Java 1.2 | 46 | 0 |
| Java 1.3 | 47 | 0 |
| Java 1.4 | 48 | 0 |
| Java 5 | 49 | 0 |
| Java 6 | 50 | 0 |
| Java 7 | 51 | 0 |
| Java 8 | 52 | 0 |
| Java 9 | 53 | 0 |
| Java 10 | 54 | 0 |
| Java 11 | 55 | 0 |
| Java 12 | 56 | 0 |
| Java 13 | 57 | 0 |
| Java 14 | 58 | 0 |
| Java 15 | 59 | 0 |
| Java 16 | 60 | 0 |
| Java 17 | 61 | 0 |
| Java 18 | 62 | 0 |
| Java 19 | 63 | 0 |
| Java 20 | 64 | 0 |
| Java 21 | 65 | 0 |
| Java 22 | 66 | 0 |
| Java 23 | 67 | 0 |
| Java 24 | 68 | 0 |
| Java 25 | 69 | 0 |
| Java 26 | 70 | 0 |

Với các release từ Java 5 trong bảng, quy luật tiện nhớ là **major = số release + 44**. Chẳng hạn 17 + 44 = 61, 21 + 44 = 65. Các phiên bản Java 1.x cũ cần đối chiếu riêng: không dùng công thức cho Java 1.1.

Bảng cho biết **class file format version**, không tự nói runtime đã hỗ trợ một API cụ thể hay bản phân phối JDK nào được cài đặt. Một Java 17 runtime thông thường hỗ trợ class file với major tối đa 61; một Java 11 runtime thông thường hỗ trợ tối đa 55. Khi gặp major lớn hơn giới hạn, JVM có thể ném `UnsupportedClassVersionError`.

Nếu phải giải mã một major chưa có trong bảng và biết nó thuộc quy luật Java hiện đại, có thể tính release bằng `major - 44`; vẫn cần đối chiếu đặc tả và mức hỗ trợ thực tế của runtime, nhất là khi có preview features.

## 4. Xem major/minor bằng javap -verbose

Lệnh `javap` nằm trong JDK và có thể hiển thị metadata của class file. Tạo file **`HelloVersion.java`**:

~~~java
public final class HelloVersion {
    public static void main(String[] args) {
        System.out.println("Hello, bytecode!");
    }
}
~~~

Trên máy có JDK 17, chạy từ thư mục chứa file:

~~~bash
javac -encoding UTF-8 --release 17 HelloVersion.java
javap -verbose HelloVersion
java HelloVersion
~~~

`javac` thường không in stdout khi biên dịch thành công. Kết quả đầy đủ của `javap -verbose` còn gồm constant pool và các thuộc tính; phần quan trọng cần tìm là:

~~~text
  minor version: 0
  major version: 61
~~~

**Stdout chính xác của lệnh `java HelloVersion`:**

~~~text
Hello, bytecode!
~~~

Bạn cũng có thể chỉ định trực tiếp file đã biên dịch:

~~~bash
javap -verbose HelloVersion.class
~~~

`javap` đọc nội dung class file hoặc class tìm được theo classpath. Nếu có nhiều JAR chứa cùng binary name, hãy cung cấp **đường dẫn cụ thể đến file** hoặc `-classpath` phù hợp; nếu không, bạn có thể vô tình đọc nhầm bản class khác.

### Đọc một class trong JAR

Giả sử file `app.jar` thực sự chứa `com/example/app/Main.class`. Dùng:

~~~bash
javap -verbose -classpath app.jar com.example.app.Main
~~~

Dòng lệnh là **ví dụ phương pháp**, chỉ chạy khi JAR và class nói trên tồn tại. Khi xem class bằng `javap`, tìm `major version` và `minor version` của class cụ thể. **JAR không có một major version duy nhất** nếu nó chứa nhiều class được biên dịch ở các mức khác nhau.

Nếu muốn quan sát tất cả tệp class bên trong, trước hết liệt kê:

~~~bash
jar --list --file app.jar
~~~

Sau đó kiểm tra các class cần thiết (đặc biệt là các class đầu vào chương trình và dependency có khả năng bị lỗi).

## 5. Đọc byte header bằng chương trình Java 17 chạy độc lập

`javap` là công cụ tiện nhất, nhưng có thể tự xác minh header mà không cần thư viện ngoài. Tạo tệp **`ClassVersionReader.java`** cùng thư mục với `HelloVersion.java`:

~~~java
import java.io.DataInputStream;
import java.io.FileInputStream;
import java.io.IOException;

public final class ClassVersionReader {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ClassVersionReader <file.class>");
            return;
        }

        try (DataInputStream in =
                     new DataInputStream(new FileInputStream(args[0]))) {
            int magic = in.readInt();
            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();

            System.out.printf("magic: 0x%08X%n", magic);
            System.out.printf("minor version: %d%n", minor);
            System.out.printf("major version: %d%n", major);

            if (magic != 0xCAFEBABE) {
                System.err.println("Not a Java class file");
            }
        }
    }
}
~~~

Đặt cả hai file trong cùng thư mục, chạy bằng JDK 17:

~~~bash
javac -encoding UTF-8 --release 17 HelloVersion.java ClassVersionReader.java
java ClassVersionReader HelloVersion.class
~~~

**Stdout chính xác:**

~~~text
magic: 0xCAFEBABE
minor version: 0
major version: 61
~~~

Giải thích: `DataInputStream.readInt()` đọc 4 byte big-endian, `readUnsignedShort()` đọc 2 byte unsigned nên minor = 0 hoặc 65535 đều được biểu diễn đúng. `try-with-resources` bảo đảm đóng stream. File quá ngắn sẽ gây `EOFException`; đây là chương trình **đọc header tối giản**, chưa phải bộ kiểm tra class file hoàn chỉnh.

### Biên dịch cùng mã cho Java 8

Với một JDK có hỗ trợ target `--release 8` (chẳng hạn JDK 17), chạy:

~~~bash
javac -encoding UTF-8 --release 8 HelloVersion.java ClassVersionReader.java
java ClassVersionReader HelloVersion.class
~~~

**Stdout chính xác khi hai nguồn vừa được biên dịch lại thành công:**

~~~text
magic: 0xCAFEBABE
minor version: 0
major version: 52
~~~

Source code không đổi, nhưng class file major thay đổi **61 → 52** vì target release thay đổi. Chương trình `ClassVersionReader` cũng được tạo thành class major 52, nên có thể chạy trên runtime Java 8 nếu runtime có các dependency/API cần thiết. Những ví dụ trên sử dụng API có mặt trong Java 8.

Nếu build có nhiều module hoặc JAR, cần kiểm tra **tất cả class liên quan** chứ không chỉ class có `main`. Một `Main.class` major 52 vẫn có thể phụ thuộc vào thư viện chứa major 61, gây lỗi khi JVM Java 8 cần nạp class đó.

## 6. UnsupportedClassVersionError xảy ra khi nào?

`java.lang.UnsupportedClassVersionError` là một dạng `LinkageError` (cụ thể là subclass của `ClassFormatError`), được JVM ném khi class file version không được hỗ trợ.

Ví dụ điển hình:

- `javac --release 17` tạo `HelloVersion.class` major 61.
- Chạy `java HelloVersion` bằng JVM **Java 11** (giới hạn major 55).
- JVM Java 11 không hiểu định dạng class file major 61 và từ chối tải class.

Thông báo lỗi có thể gần như sau (minh họa, phần đường dẫn/tên class và câu chữ phụ thuộc JDK):

~~~text
java.lang.UnsupportedClassVersionError:
  HelloVersion has been compiled by a more recent version of the Java Runtime
  (class file version 61.0),
  this version of the Java Runtime only recognizes class file versions up to 55.0
~~~

Đọc thông báo theo từng phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `HelloVersion` | Class mà runtime đang không thể tải ở thời điểm báo lỗi |
| `class file version 61.0` | Bytecode cần Java 17 trở lên để hỗ trợ major 61, nếu không bị ràng buộc đặc biệt bởi preview |
| `up to 55.0` | Runtime đang hỗ trợ tối đa major 55, tương ứng Java 11 |
| `UnsupportedClassVersionError` | Vấn đề về **phiên bản định dạng class file** chứ không phải lỗi `import` |

Một class ở dependency cũng có thể là nguyên nhân. Ví dụ `Main` major 55 chạy trên Java 11, nhưng gọi `LibraryService` major 61; ứng dụng có thể khởi động rồi mới ném lỗi khi cần tải `LibraryService`. Vì thế **class được nêu trong exception** mới là điểm bắt đầu điều tra phù hợp.

### Có phải luôn là JDK mới hơn JRE không?

Trường hợp phổ biến là **compiler tạo bytecode mới hơn JVM runtime**. Tuy nhiên còn các biến thể như preview class file có minor đặc biệt mà runtime không cho phép, hoặc file class có cặp version không được hỗ trợ. Vì vậy hãy đọc **cả major và minor** và kiểm tra runtime thật, thay vì mặc định mọi lỗi chỉ cần nâng JDK.

## 7. Minor version thông thường và preview feature

Trong đa số class file Java hiện đại **không dùng preview**, `minor_version = 0`.

Đối với class file có **major version 56 trở lên (Java 12+)**, định dạng class file quy định minor phải là **0 hoặc 65535**. Khi minor = **65535** (`0xFFFF`), class file đánh dấu **phụ thuộc preview feature** của Java release tương ứng.

Ví dụ:

| Major.minor | Diễn giải |
| --- | --- |
| `61.0` | Class file Java 17 thông thường |
| `61.65535` | Class file Java 17 dùng preview feature |
| `65.0` | Class file Java 21 thông thường |
| `65.65535` | Class file Java 21 dùng preview feature |

Đối với class preview:

- Compiler thường cần bật `--enable-preview` và chọn đúng `--release N` hoặc `--source N` mà compiler hỗ trợ preview.
- Runtime cần hỗ trợ **đúng Java release** tương ứng với class preview và thường phải chạy với `--enable-preview`.
- Một runtime Java mới hơn **không mặc nhiên chạy class preview của release cũ**, kể cả khi hỗ trợ major version lớn hơn.
- `--enable-preview` **không** làm JVM cũ hiểu một major class file mới hơn nó hỗ trợ.

### Ví dụ preview trên JDK 17

Java 17 có **pattern matching for switch** ở trạng thái preview. Tạo **`PreviewDemo.java`**:

~~~java
public final class PreviewDemo {
    static String describe(Object value) {
        return switch (value) {
            case String text -> "String:" + text;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
    }
}
~~~

Chạy **bằng JDK 17**:

~~~bash
javac --enable-preview --release 17 PreviewDemo.java
javap -verbose PreviewDemo
java --enable-preview PreviewDemo
~~~

Lệnh `javap` sẽ hiển thị phần version:

~~~text
  minor version: 65535
  major version: 61
~~~

**Stdout của chương trình:**

~~~text
String:Java
~~~

`javac` và `java` có thể in thêm thông báo về preview features lên stderr; những dòng thông báo phụ thuộc JDK, không thuộc stdout của chương trình. Nếu bỏ `--enable-preview` ở lệnh chạy, JVM không cho phép nạp class preview như class thông thường. Đoạn này dùng cú pháp preview **cụ thể của JDK 17**; với JDK khác, hãy chọn ví dụ preview và cờ phù hợp bản Java đó.

**Lưu ý:** Chỉ bật `--enable-preview` khi compiler thực sự sinh class phụ thuộc preview feature mới khiến class liên quan mang minor = 65535. Không nên suy luận rằng mọi class trong một lần build có bật cờ đó đều chắc chắn có minor = 65535.

## 8. Dùng --release để tạo bytecode tương thích

Nếu bạn phát triển bằng JDK mới nhưng cần chạy ứng dụng trên Java cũ hơn, nên dùng `javac --release N` khi bản compiler hỗ trợ target đó.

Ví dụ JDK 17:

~~~bash
javac --release 8 -encoding UTF-8 -d out8 HelloVersion.java
javac --release 17 -encoding UTF-8 -d out17 HelloVersion.java
javap -verbose out8/HelloVersion.class
javap -verbose out17/HelloVersion.class
~~~

Hai lệnh `javap` sẽ lần lượt cho thấy:

~~~text
out8/HelloVersion.class  -> major version: 52, minor version: 0
out17/HelloVersion.class -> major version: 61, minor version: 0
~~~

**Các dòng trên là bản tóm tắt** kết quả, không phải output nguyên văn của `javap`. Trước khi chạy, hãy tạo `out8` và `out17` hoặc để compiler tạo thư mục theo khả năng của toolchain; một cách tường minh trên Bash là `mkdir -p out8 out17`. Tùy phiên bản JDK, không phải mọi target release cũ đều được hỗ trợ.

### --release khác -source và -target

| Tùy chọn | Điều chỉnh |
| --- | --- |
| `--source N` | Phiên bản cú pháp và quy tắc source language được compiler chấp nhận |
| `--target N` | Mục tiêu tạo bytecode/class file version |
| `--release N` | Phối hợp source language, target class file và **API Java platform** khả dụng ở release N |

Nếu chỉ dùng `-source 8 -target 8` với một JDK mới, bạn có thể vô tình compile mã gọi **API của Java platform mới hơn**, trong khi class file vẫn mang major 52. Khi chạy trên Java 8, lỗi có thể là `NoSuchMethodError` hoặc lỗi linkage khác, mặc dù major 52 được JVM chấp nhận.

`--release 8` giúp compiler kiểm tra mã theo API platform của Java 8 và ngăn trường hợp dựa vào API mới thuộc JDK. Tuy nhiên **`--release` không tự kiểm tra mọi thư viện bên thứ ba** trên classpath của bạn có tương thích runtime đích hay không. Bạn vẫn phải kiểm soát version của dependency và kiểm thử bằng runtime mục tiêu.

Ví dụ code sau dùng `String.repeat(int)` (API có từ Java 11):

~~~java
public final class RepeatDemo {
    public static void main(String[] args) {
        System.out.println("A".repeat(3));
    }
}
~~~

Khi dùng compiler có target Java 8:

~~~bash
javac --release 8 RepeatDemo.java
~~~

Compiler sẽ **từ chối** vì API `String.repeat` không tồn tại trong Java 8. Với JDK 17 và `-source 8 -target 8` không kèm giới hạn platform API thích hợp, mã có thể biên dịch ra major 52, nhưng khi chạy trên Java 8 sẽ thiếu method tương ứng. Đây là minh họa vì sao **major tương thích chưa đủ chứng minh API tương thích**.

## 9. Xác định đúng javac và java thực tế

Trên máy phát triển có thể cài nhiều JDK/JRE. Bạn chạy `javac` của JDK 21 nhưng `java` trong PATH lại là runtime Java 11; từ đó xuất hiện lỗi dù IDE báo mọi thứ đều đúng.

Kiểm tra:

~~~bash
javac -version
java -version
~~~

Các lệnh này cho biết phiên bản tool được terminal chọn. Nếu cần kiểm tra đường dẫn executable:

**Linux/macOS:**

~~~bash
command -v javac
command -v java
~~~

**Windows PowerShell:**

~~~powershell
Get-Command javac
Get-Command java
~~~

**Windows CMD:**

~~~bat
where javac
where java
~~~

Không có output cố định vì đường dẫn phụ thuộc máy. Trên các môi trường build/CI, biến `JAVA_HOME` và thứ tự `PATH` có thể quyết định Java toolchain được sử dụng; IDE hoặc Gradle/Maven có thể chọn JDK khác terminal. Khi gặp lỗi, ghi lại **toolchain compile**, **runtime deploy** và **class version thật trong artifact**.

### Triển khai: đừng chỉ nhìn JDK của máy build

Một pipeline dùng JDK 21 để biên dịch rồi triển khai trên server Java 17 sẽ cần class file major không vượt giới hạn runtime (Java 17 hỗ trợ major 61 thông thường), và còn phải dùng API/dependency phù hợp.

Những nơi cần kiểm tra gồm:
- JDK của CI worker.
- Cấu hình `--release`/toolchain và plugin Java compiler của build.
- JRE/JDK được image Docker hoặc máy chạy ứng dụng cung cấp.
- Các thư viện đã được đóng vào artifact.
- Các class sinh bằng annotation processor, code generation, bytecode manipulation hoặc plugin khác.

Ứng dụng có thể gồm class được tạo từ nhiều compiler hoặc build task; đừng suy ra mọi class file dùng cùng major chỉ vì một thiết lập chung.

## 10. UnsupportedClassVersionError so với các lỗi liên quan

| Lỗi/triệu chứng | Giai đoạn | Chẩn đoán đầu tiên |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM nạp/định nghĩa class | Đọc major.minor của class báo lỗi, đối chiếu runtime |
| `NoSuchMethodError` | Liên kết/lời gọi runtime | API class runtime khác API compile-time; kiểm tra chữ ký method |
| `NoClassDefFoundError` | Nạp/liên kết/khởi tạo runtime | Class cần thiết không thể được cung cấp hoặc đã khởi tạo lỗi |
| `ClassNotFoundException` | API nạp class theo tên | Class loader không tìm được class được yêu cầu |
| `ClassFormatError` | Kiểm tra định dạng class runtime | Bytecode không hợp lệ; lưu ý `UnsupportedClassVersionError` là subtype |
| `Unsupported major.minor version X.Y` | Thông báo của một số JVM cũ | Phiên bản class file không được runtime hỗ trợ |
| `invalid source release: N` | Compile | Bản compiler không hỗ trợ source release đã yêu cầu |
| `release version N not supported` | Compile | Bản compiler không hỗ trợ target `--release N` |
| `cannot find symbol` với API platform | Compile | API không có theo release cấu hình, hoặc sai dependency/import |
| `Preview features are not enabled` hoặc thông báo tương đương | Compile/runtime | Thiếu cờ preview đúng release hoặc dùng class preview không phù hợp |

**Không nên chữa `UnsupportedClassVersionError` bằng thêm `import` hay sửa package name:** compiler và JVM có thể tìm thấy class nhưng định dạng của nó không được chấp nhận. Cũng không nên mặc định hạ major bằng cách sửa hai byte header: body bytecode, constant pool và attributes có thể cần tính năng của phiên bản mới; chỉnh header thủ công sẽ không chuyển đổi bytecode sang một phiên bản hợp lệ.

## 11. Cách xử lý khi runtime quá cũ

Giả sử log nêu class file `65.0`, runtime chỉ hỗ trợ tới `61.0`.

**Bước 1: Đọc thông báo.** Major 65 là Java 21, major 61 là Java 17. Class đã được biên dịch ở mức Java 21 nhưng runtime hiện tại hỗ trợ class file thông thường tới Java 17.

**Bước 2: Tìm class gây lỗi.** Nếu log nói `com.example.lib.Parser`, hãy tìm JAR/thư mục chứa class ấy, không chỉ kiểm tra class `Main`. Xác định class bằng `javap -verbose -classpath path/to/library.jar com.example.lib.Parser`.

**Bước 3: Xác nhận runtime thật.** Chạy `java -version` trong **chính môi trường xảy ra lỗi**: container, service, pipeline hoặc terminal dùng để khởi động. Một máy có nhiều JDK có thể khiến terminal và ứng dụng chọn hai executable khác nhau.

**Bước 4: Chọn hướng sửa phù hợp:**

1. **Nâng runtime** lên JDK/JRE đủ mới, nếu chính sách triển khai cho phép và toàn bộ hệ thống tương thích.
2. **Biên dịch lại với `--release 17`** nếu mã nguồn và API thực sự hỗ trợ target Java 17. Xây dựng toàn bộ module cần thiết bằng toolchain/cấu hình nhất quán.
3. **Chọn phiên bản dependency** hỗ trợ Java 17 nếu thư viện bên thứ ba chỉ phát hành class major 65. Bạn thường không có quyền hoặc đủ thông tin để biên dịch lại bytecode của vendor.
4. **Phân tách/thay thế thành phần** nếu một thư viện bắt buộc Java 21 và ứng dụng phải duy trì Java 17; đây là thay đổi kiến trúc cần đánh giá.
5. **Nếu minor = 65535**, kiểm tra preview, release cụ thể và cờ runtime thay vì chỉ so sánh major.

**Bước 5: Kiểm tra lại artifact và chạy trên target runtime.** Đọc class version của các class liên quan và chạy integration/smoke test ở môi trường đúng version. Chỉ việc `javac` trả exit code 0 trên máy build không chứng minh runtime đích có thể chạy toàn bộ dependency graph.

### Nếu compiler báo lỗi vì source dùng tính năng mới

Ví dụ source có record:

~~~java
public record Point(int x, int y) {
}
~~~

`record` là tính năng chuẩn từ Java 16. Compile bằng `javac --release 8` không hợp lệ vì target source Java 8 không hỗ trợ record. Muốn chạy ứng dụng trên Java 8, cần thiết kế lại source theo cú pháp và API Java 8; không thể chỉ đổi flag mà giữ nguyên tính năng ngôn ngữ mới.

## 12. Khi một JAR chứa nhiều mức class version

Không có quy tắc bắt buộc rằng mọi `.class` trong một JAR đều mang cùng major. Có thể xảy ra:

- Dự án ghép các tệp class đã build từ những module ở mức target khác nhau.
- Một thư viện có class tương thích baseline Java cũ nhưng kèm class được tạo cho release mới.
- **Multi-release JAR** có đường dẫn đặc biệt `META-INF/versions/N/...` và manifest khai báo `Multi-Release: true`, cho phép runtime phù hợp chọn phiên bản class/resource theo release.

Ví dụ cấu trúc khái niệm:

~~~text
example.jar
├── META-INF/MANIFEST.MF                 (Multi-Release: true)
├── com/example/Feature.class            (bản cơ sở)
└── META-INF/versions/17/
    └── com/example/Feature.class        (bản cho Java 17)
~~~

Đây là cấu trúc **minh họa**, không phải JAR mẫu đã tạo trong bài. Bản class cơ sở có thể có major 52, còn bản cho Java 17 có major 61. JVM có hỗ trợ multi-release JAR có thể chọn bản theo release của runtime, tuân theo điều kiện manifest và các quy tắc phiên bản của định dạng JAR.

Khi chẩn đoán, hãy xác định **entry cụ thể đang được tải**, không chỉ đọc một class file bất kỳ trong JAR. Với `javap` có tùy chọn `--multi-release N` để xem entry ứng với phiên bản trong multi-release JAR nếu công cụ/JAR hỗ trợ; kết quả vẫn cần đối chiếu cơ chế nạp class thực tế.

## 13. Preview class file không phải bản Java chạy đa phiên bản

Giả sử một class có header `61.65535`:

- Java 17 với `--enable-preview` có thể chấp nhận **nếu** class hợp lệ và preview tương ứng được hỗ trợ.
- Java 17 không bật preview sẽ không chấp nhận như class thông thường.
- Java 18 không được coi `61.65535` là class preview Java 18, ngay cả khi Java 18 hiểu nhiều class file major thấp hơn. Preview có ràng buộc với **đúng release**.
- Java 11 không hỗ trợ major 61, nên bật preview không thể giải quyết.

Vì thế với lỗi nhắc đến preview, cần đọc **minor** cùng **major**, và đảm bảo compile/runtime cùng release preview. Tốt nhất là tránh đóng class preview vào thư viện dùng chung cần tương thích lâu dài nếu không có yêu cầu rõ ràng.

## 14. Các câu hỏi kiểm tra và đáp án

**Câu 1.** `javap -verbose` in `major version: 52` và `minor version: 0`. Tệp class hướng tới release nào?

**Đáp án:** Class file format của Java 8. Tuy nhiên vẫn phải kiểm tra các API và dependency runtime để kết luận ứng dụng hoàn toàn tương thích Java 8.

**Câu 2.** Tại sao `major 61` không nhất thiết có nghĩa developer đã chạy `javac` của JDK 17?

**Đáp án:** Một compiler mới hơn có thể tạo target Java 17 bằng `--release 17` hoặc cấu hình thích hợp. Major phản ánh **đích class file**, không trực tiếp phản ánh version executable compiler.

**Câu 3.** JVM Java 11 báo “class file version 61.0, runtime recognizes up to 55.0”. Hai con số nói gì?

**Đáp án:** Class cần định dạng Java 17; runtime chỉ hỗ trợ tới định dạng Java 11. Cần runtime mới hơn hoặc class được biên dịch lại với target phù hợp.

**Câu 4.** Khi xem tám byte đầu `CA FE BA BE 00 00 00 41`, major bằng bao nhiêu?

**Đáp án:** `0x0041 = 65`, tương ứng Java 21; minor = 0. Dữ liệu dùng big-endian.

**Câu 5.** `minor = 65535` đối với major 61 báo điều gì?

**Đáp án:** Class file Java 17 mang đánh dấu preview feature. Nó cần điều kiện hỗ trợ preview của đúng release Java 17; không phải version Java “61.65535”.

**Câu 6.** Có thể hạ major từ 65 xuống 61 bằng hex editor để JVM Java 17 chạy được không?

**Đáp án:** Không có bảo đảm và không phải giải pháp hợp lệ. Bytecode/attributes/API có thể không tương thích. Phải biên dịch lại với source và target tương ứng hoặc nâng runtime.

**Câu 7.** Vì sao `Main.class` major 52 vẫn có thể thất bại trên Java 8?

**Đáp án:** Một class phụ thuộc có thể có major lớn hơn, hoặc chương trình gọi API không có trong runtime Java 8. Major của một class riêng lẻ không bảo đảm toàn bộ ứng dụng chạy được.

**Câu 8.** `--release 8` và `-target 8` có tương đương hoàn toàn?

**Đáp án:** Không. `--release 8` còn giới hạn API Java platform theo Java 8, giúp phát hiện việc gọi API được thêm sau Java 8. Chỉ đặt target bytecode không cung cấp cùng mức kiểm tra platform API.

## 15. Checklist khi điều tra lỗi trong dự án thực

1. Ghi lại **tên class** trong `UnsupportedClassVersionError` và thông báo **major.minor**.
2. Dùng bảng major để suy ra Java release tối thiểu tương ứng của **class file**.
3. Xác định **`java -version` của tiến trình chạy lỗi**, không chỉ của terminal hoặc IDE.
4. Dùng `javap -verbose` hoặc công cụ đọc header để xác minh class file **thực sự được triển khai**.
5. Kiểm tra class đó nằm trong application output, dependency JAR, generated bytecode hay multi-release JAR.
6. Kiểm tra `javac -version`, `--release`, compiler toolchain, cấu hình Gradle/Maven và version target của từng module.
7. Nếu thấy **minor 65535**, xác định cờ preview và release tương ứng ở cả compile/runtime.
8. Quyết định nâng runtime, hạ target biên dịch hợp lệ hoặc thay dependency; không sửa header bytecode thủ công.
9. Chạy lại trên đúng runtime mục tiêu, xác minh tất cả class và API được sử dụng, lưu bằng chứng build/triển khai để lỗi không tái diễn.

## Ghi nhớ

- Header `.class` bắt đầu bằng **magic = 0xCAFEBABE**, sau đó **minor (2 byte)** rồi **major (2 byte)**, đều big-endian.
- Class file thường dùng **minor 0**; từ **Java 12/major 56** trở lên, **minor 65535** đánh dấu class phụ thuộc preview của release tương ứng.
- Các mốc hữu ích: **Java 8 → 52**, **Java 11 → 55**, **Java 17 → 61**, **Java 21 → 65**.
- `UnsupportedClassVersionError` xảy ra khi JVM không hỗ trợ version class file được nạp; thông báo nói rõ version của class và giới hạn runtime.
- Dùng **`javap -verbose`** để xem version, **`java -version`** để xem runtime thật và **`javac --release N`** khi cần build theo Java mục tiêu.
- Bytecode major phù hợp là **điều kiện cần, chưa đủ** cho tương thích API/dependency; hãy kiểm thử trên runtime thực tế.
