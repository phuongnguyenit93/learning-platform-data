# Cấu trúc ClassFile: magic number, major version và minor version

Một tệp `.class` của Java là **tệp nhị phân theo định dạng ClassFile do JVM Specification quy định**. Nó thường được trình biên dịch `javac` tạo ra từ mã nguồn, nhưng cũng có thể được các công cụ sinh hoặc biến đổi bytecode tạo ra. ClassFile chứa định danh định dạng, phiên bản class file, constant pool, mô tả lớp, trường, phương thức và các thuộc tính. JVM dùng các thông tin này để nhận diện, đọc, kiểm tra, liên kết và thực thi lớp.

Ba trường đầu tiên của cấu trúc ClassFile chính là trọng tâm bài học:

- **`magic`**: bốn byte đầu có giá trị **`0xCAFEBABE`**, giúp nhận diện đây là dữ liệu dự kiến theo định dạng ClassFile.
- **`minor_version`**: số nguyên không dấu **16 bit**, cho biết phiên bản phụ theo quy tắc của định dạng class file.
- **`major_version`**: số nguyên không dấu **16 bit**, cho biết phiên bản chính và là cơ sở quan trọng để JVM quyết định có hỗ trợ class file hay không.

Một class file mang đúng magic number **chưa chắc hợp lệ hoặc thực thi được**. JVM còn phải đọc và kiểm tra cấu trúc còn lại, kiểu dữ liệu, bytecode, khả năng tương thích phiên bản, classpath/module path và những phụ thuộc được tham chiếu.

## 1. ClassFile là cấu trúc nhị phân, không phải mã nguồn Java

Sơ đồ đơn giản của byte đầu tiên trong một `.class` thông thường được biên dịch cho Java 17:

```text
Offset (hex)   00 01 02 03 | 04 05 | 06 07 | 08 09 | ...
Giá trị        CA FE BA BE | 00 00 | 00 3D | ...   | ...
                  magic       minor    major   constant_pool_count ...

magic         = 0xCAFEBABE
minor_version = 0
major_version = 0x003D = 61
```

Mỗi trường **`u1`** có 1 byte, **`u2`** có 2 byte và **`u4`** có 4 byte. Theo định dạng ClassFile, các giá trị nhiều byte được lưu ở thứ tự **big-endian** (byte quan trọng nhất đứng trước). Vì vậy:

- Dãy byte `CA FE BA BE` biểu diễn số 32 bit `0xCAFEBABE`.
- Dãy `00 00` biểu diễn `minor_version = 0`.
- Dãy `00 3D` biểu diễn `major_version = 0x003D = 61`, ứng với class-file version chuẩn của Java 17.

**Đây là ví dụ header, không phải toàn bộ file.** Byte ở offset 8–9 là `constant_pool_count`; giá trị thực tế phụ thuộc số mục trong constant pool do compiler tạo. Không đoán nó từ ví dụ nếu chưa đọc tệp.

### Vì sao không thể mở `.class` như văn bản?

Tệp `.java` chứa ký tự mã nguồn; `.class` chứa một trình tự có cấu trúc gồm byte, số nguyên, chỉ mục, chuỗi mã hóa và bytecode. Trình soạn thảo văn bản có thể hiển thị ký tự vô nghĩa khi cố diễn giải byte nhị phân thành Unicode. Dùng `javap -verbose`, trình xem hex hoặc một chương trình đọc nhị phân để kiểm tra. Các lệnh trong tệp `.class` là **JVM bytecode**, không phải trực tiếp mã máy x86-64 hay ARM.

## 2. Cấu trúc tổng quát của `ClassFile`

Phần đầu và các nhóm thành phần được mô tả trong JVM Specification có dạng:

```text
ClassFile {
    u4             magic;
    u2             minor_version;
    u2             major_version;
    u2             constant_pool_count;
    cp_info        constant_pool[constant_pool_count - 1];
    u2             access_flags;
    u2             this_class;
    u2             super_class;
    u2             interfaces_count;
    u2             interfaces[interfaces_count];
    u2             fields_count;
    field_info     fields[fields_count];
    u2             methods_count;
    method_info    methods[methods_count];
    u2             attributes_count;
    attribute_info attributes[attributes_count];
}
```

Đây là **mô tả cấu trúc dữ liệu của định dạng file**, không phải cú pháp Java để đặt vào `ClassFile.java`. Ký hiệu `u1/u2/u4` là các số nguyên không dấu có độ rộng cố định, không phải kiểu biến nguyên thủy độc lập của Java.

| Thành phần | Chức năng chính |
| --- | --- |
| `magic` | Dấu hiệu nhận diện định dạng ClassFile |
| `minor_version`, `major_version` | Cặp phiên bản để JVM xác định quy tắc đọc và hỗ trợ |
| `constant_pool_count`, `constant_pool` | Bảng các hằng số và symbolic reference cho tên lớp, trường, phương thức, chuỗi, literal, descriptor... |
| `access_flags` | Các cờ mô tả thuộc tính của class/interface/module như `public`, `final`, `abstract` ở mức định dạng |
| `this_class`, `super_class` | Chỉ mục tham chiếu tới biểu diễn lớp hiện tại và lớp cha tương ứng trong constant pool |
| `interfaces_count`, `interfaces` | Danh sách interface được lớp hoặc interface này khai báo mở rộng/triển khai |
| `fields_count`, `fields` | Mô tả các field, kiểu, cờ và thuộc tính liên quan |
| `methods_count`, `methods` | Mô tả các method, descriptor, cờ và thuộc tính; một method có mã có thể chứa thuộc tính `Code` |
| `attributes_count`, `attributes` | Metadata như `SourceFile`, `Signature`, `BootstrapMethods`, `InnerClasses`... khi áp dụng |

Ba trường `magic`, `minor_version`, `major_version` **nằm tại vị trí cố định**. Từ `constant_pool` trở đi, kích thước các khối có thể biến đổi. Không thể tìm `methods_count` bằng một offset cố định giống như major version; phải giải mã tuần tự các thành phần trước đó.

**Chú ý `constant_pool_count`:** bảng constant pool được đánh chỉ số bắt đầu từ **1** và thông thường có `constant_pool_count - 1` vị trí được chỉ số hóa. Các hằng `CONSTANT_Long` và `CONSTANT_Double` chiếm hai **vị trí chỉ số** theo quy tắc format dù nội dung là một mục; vị trí tiếp theo bị dành riêng. Vì vậy số mục thực sự không nhất thiết bằng số vị trí chỉ số sử dụng.

## 3. Magic number: bốn byte `CA FE BA BE`

### 3.1. Định nghĩa

Đầu class file phải có đúng:

```text
CA FE BA BE
```

Viết dưới dạng số nguyên hex 32 bit: **`0xCAFEBABE`**. Trong tài liệu Java, đôi khi các byte được viết nối liền thành `CAFEBABE`, nhưng đây là **một trường `u4`**, không phải bốn ký tự ASCII `C`, `A`, `F`, `E`.

Ví dụ so sánh:

```text
Byte của ClassFile:  CA FE BA BE
Byte ASCII "CAFE":  43 41 46 45
```

Hai chuỗi byte khác nhau hoàn toàn. Khi xem hex dump, phải kiểm tra **byte thực**, không phải nội dung chữ được render.

### 3.2. Magic dùng để làm gì và không làm được gì?

Magic number giúp công cụ/JVM sớm phát hiện một đầu vào không có header đúng định dạng. Nếu file bắt đầu bằng `50 4B ...`, chẳng hạn, nhiều khả năng đó là một ZIP/JAR container chứ không phải class file thô: JAR có thể **chứa nhiều `.class`**, nhưng bản thân JAR không bắt đầu bằng magic của ClassFile.

Magic **không phải chữ ký mật mã**, không xác minh nguồn gốc hoặc tính toàn vẹn của file. Ai cũng có thể tạo một tệp gồm bốn byte `CA FE BA BE` mà không có cấu trúc còn lại; tệp đó vẫn không phải class file hợp lệ. JVM phải kiểm tra tiếp phiên bản, cấu trúc constant pool, thuộc tính và bytecode.

## 4. `major_version`: phiên bản ClassFile mà JVM hỗ trợ

**`major_version`** nằm tại offset byte 6–7 (đếm từ 0). Nó thường tăng theo các bản phát hành Java, thể hiện cấp độ class-file format của tệp. Một JVM cũ **không bắt buộc** hiểu mọi định dạng class file được biên dịch bằng JDK mới.

Một số mốc thường gặp:

| Java SE dùng làm đích biên dịch | `major_version` | Hex của trường `u2` |
| --- | ---: | --- |
| Java 8 | 52 | `00 34` |
| Java 11 | 55 | `00 37` |
| Java 17 | 61 | `00 3D` |
| Java 21 | 65 | `00 41` |
| Java 25 | 69 | `00 45` |

Các mốc trên áp dụng cho class file chuẩn của từng release, thường có **`minor_version = 0`**. Với các Java phiên bản lịch sử, quy tắc minor/major có thể khác; không nên áp dụng máy móc công thức tuyến tính cho toàn bộ lịch sử Java.

Ví dụ:

- Biên dịch cho Java 17 thường tạo class file phiên bản **61.0**.
- Biên dịch cho Java 21 thường tạo class file phiên bản **65.0**.
- Một runtime chỉ hiểu class file tối đa phiên bản **61** sẽ từ chối class file yêu cầu **65**, thường bằng **`UnsupportedClassVersionError`** khi thử nạp lớp.
- JVM mới hơn có thể hỗ trợ các class file phiên bản cũ hơn, nhưng **chỉ tương thích class format chưa đủ**: dependency, API, quyền truy cập/module, hành vi runtime hay thư viện native vẫn có thể gây lỗi.

### 4.1. JDK chạy compiler khác với release đích

Nếu bạn dùng JDK 21 để chạy:

```bash
javac --release 17 Hello.java
```

thì compiler được yêu cầu tạo output phù hợp **Java 17**, bao gồm class-file version 61 và giới hạn API nền tảng được hỗ trợ bởi release đích. Tức là **JDK của công cụ biên dịch** có thể mới hơn **release mà class file nhắm tới**.

Ngược lại, chỉ vì máy phát triển có JDK 21 không có nghĩa mọi class được sinh ra **bắt buộc** là major 65. Phải kiểm tra cờ biên dịch và tệp kết quả.

Nếu muốn đảm bảo bytecode/runtime API cho một release cụ thể, ưu tiên `--release N` khi JDK đang dùng hỗ trợ đích đó. `-source N` chỉ điều khiển cấp ngôn ngữ; `-target N` điều khiển định dạng output, nhưng kết hợp hai cờ đó **không tự động bảo đảm** không dùng nhầm API chuẩn của JDK mới, trong khi `--release` có kiểm soát phần này.

### 4.2. Phiên bản file khác phiên bản runtime/API

Cần phân biệt:

```text
JDK dùng để chạy javac   → toolchain version
--release hoặc -target   → target bytecode / class-file major version
java --version           → Java runtime đang khởi chạy
javap -verbose           → phiên bản được ghi trong file .class cụ thể
```

Không thể kết luận target chỉ từ tên thư mục chứa mã nguồn hoặc tên JAR. Trong một số trường hợp, cùng một JAR còn có thể chứa **nhiều biến thể class file theo release** (multi-release JAR); vì vậy phải kiểm tra **đúng entry class file** đang được chọn.

## 5. `minor_version`: phiên bản phụ và preview class file

**`minor_version`** nằm tại offset byte 4–5. Nó là số nguyên không dấu từ 0 đến 65535. Với class file thông thường do compiler Java hiện đại sinh ra, minor thường bằng **0**.

### 5.1. Minor bằng 0

Đây là trường hợp thường gặp nhất khi biên dịch ứng dụng Java ổn định:

```text
CA FE BA BE 00 00 00 3D ...
             └─┘   └─┘
            minor  major
              0     61 (Java 17)
```

Đọc `61.0` là **major 61, minor 0**; đừng đọc nhầm 61.0 thành version của ngôn ngữ Java “61”.

### 5.2. Giá trị đặc biệt `65535` (`0xFFFF`) và tính năng preview

Kể từ cơ chế preview được quy định cho các Java release hiện đại, class-file version của **preview features** có thể được đánh dấu bằng `minor_version = 65535` (`0xFFFF`). Ví dụ lớp được biên dịch sử dụng preview feature của Java 17 có thể được ghi phiên bản **61.65535**.

Điểm cần nhớ:

- Class file có minor **65535** dành cho cơ chế preview theo release phù hợp, **không tương đương bản class file ổn định** với minor 0.
- Một JVM hỗ trợ preview cần **`--enable-preview`** khi khởi chạy class sử dụng preview theo luật của release đó.
- Class file mang dấu preview gắn với **release tương ứng**; không nên kỳ vọng class preview của phiên bản cũ tự động chạy trên JVM của một Java release mới hơn chỉ vì JVM mới hỗ trợ major cao hơn.
- `--enable-preview` trong `javac` chỉ hỗ trợ các preview feature của **chính release mà compiler đang dùng**, không dùng tùy ý để bật preview của một release cũ khi chạy compiler mới.

Không phải cứ có `--enable-preview` là mọi class file được tạo nhất thiết có minor 65535; điều này còn phụ thuộc mã được biên dịch có thực sự dùng tính năng cần dấu preview và quy tắc compiler/version tương ứng. Đọc **giá trị được ghi trong chính class file** luôn chính xác hơn suy đoán.

### 5.3. Kiểm tra đầy đủ cặp major/minor

Một JVM cần xem **cặp phiên bản** chứ không chỉ major, theo tập các phiên bản được hỗ trợ và quy tắc preview. Với các phiên bản class file hiện đại, minor thông thường chỉ có ý nghĩa chuẩn khi bằng 0, hoặc là 65535 trong trường hợp preview được hỗ trợ. Những tổ hợp khác có thể bị từ chối dù magic đúng.

Lỗi phiên bản thường xuất hiện **lúc lớp được tải/kiểm tra**, trước khi bytecode trong `main` bắt đầu chạy. Có thể một chương trình đã khởi chạy nhưng về sau mới gặp lỗi khi một lớp khác được nạp lần đầu.

## 6. Thực hành với JDK 17+: tạo và xem header của một class file

Để có kết quả tái lập được trên JDK 17 trở lên, dùng **`--release 17`** thay vì phụ thuộc vào target mặc định của JDK hiện tại.

### 6.1. Tạo lớp mẫu `Hello.java`

Tạo tệp **`Hello.java`** với nội dung:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, JVM!");
    }
}
```

Từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 Hello.java
java Hello
```

**Standard output của `java Hello`:**

```text
Hello, JVM!
```

Sau `javac`, bạn có tệp **`Hello.class`**, là đầu vào để xem ClassFile header. Nếu có lỗi `invalid flag: --release` hoặc `release version 17 not supported`, hãy kiểm tra `javac --version`: bạn cần JDK hỗ trợ target 17.

### 6.2. Dùng công cụ chuẩn `javap -verbose`

```bash
javap -verbose Hello
```

Trong output dài của `javap`, tìm các dòng sau:

```text
minor version: 0
major version: 61
```

Đây là các dòng về **class-file version**. `javap` còn có thể hiển thị constant pool, tên class, descriptor, flags, metadata, method và bytecode. Đừng nhầm dòng `major version` với phiên bản JVM đang chạy: `javap` đang **đọc một class file**.

Để biết JDK/runtime thực tế:

```bash
javac --version
java --version
```

Output hai lệnh này phụ thuộc vào máy; không lấy phiên bản JDK từ ví dụ trong sách rồi áp vào môi trường thực tế.

### 6.3. Đọc chính xác 8 byte đầu bằng Java

Tạo tệp **`ClassHeaderReader.java`** trong cùng thư mục với `Hello.java`:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ClassHeaderReader {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println("Usage: java ClassHeaderReader <file.class>");
            return;
        }

        Path file = Path.of(args[0]);
        try (DataInputStream input =
                     new DataInputStream(Files.newInputStream(file))) {
            long magic = Integer.toUnsignedLong(input.readInt());
            int minor = input.readUnsignedShort();
            int major = input.readUnsignedShort();

            System.out.printf("magic: 0x%08X%n", magic);
            System.out.println("minor_version: " + minor);
            System.out.println("major_version: " + major);
            System.out.println("magic_valid: " + (magic == 0xCAFEBABEL));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ClassHeaderReader.java
java ClassHeaderReader Hello.class
```

**Standard output chính xác khi `Hello.class` được biên dịch bằng lệnh ở mục 6.1:**

```text
magic: 0xCAFEBABE
minor_version: 0
major_version: 61
magic_valid: true
```

Cơ chế của chương trình:

1. `Files.newInputStream(file)` mở file dưới dạng **luồng byte nhị phân**.
2. `DataInputStream.readInt()` đọc **4 byte big-endian**; dùng `Integer.toUnsignedLong` để biểu diễn giá trị như `u4` mà không bị hiểu nhầm do dấu của Java `int`.
3. `readUnsignedShort()` đọc **2 byte big-endian** và trả về `int` trong phạm vi `0..65535`, phù hợp kiểu `u2` của ClassFile.
4. `System.out.printf("0x%08X", magic)` in 8 chữ số hex của magic.
5. So sánh với `0xCAFEBABEL` xác minh riêng **trường magic**, chưa kiểm tra toàn bộ ClassFile hoặc bytecode.

Chương trình này đọc **đúng 8 byte đầu**, không phân tích các phần phía sau. Nếu file quá ngắn, phương thức đọc có thể ném `EOFException` (một loại `IOException`); nếu không tồn tại hoặc không có quyền truy cập, thao tác mở tệp có thể ném `IOException`. Đây là **công cụ học tập**, không phải trình xác thực ClassFile đầy đủ.

### 6.4. Kiểm tra trực tiếp bằng hex viewer

Nếu có công cụ xem hex phù hợp nền tảng, mở `Hello.class` và kiểm tra tám byte đầu:

```text
CA FE BA BE 00 00 00 3D
```

Dấu cách chỉ để dễ đọc, không phải byte trong file. Công cụ hex có thể hiển thị cột offset, byte và chữ ASCII tương ứng; cột **hex bytes** mới là nguồn đáng tin để đọc header. Không sửa trực tiếp byte phiên bản để “nâng cấp/hạ cấp” tệp: định dạng, constant pool và bytecode phía sau phải thực sự tương thích.

## 7. `ClassFile` và quá trình JVM nạp lớp

Quá trình đọc class file nằm trong vòng đời runtime của JVM:

```text
File .class / bytes do class loader cung cấp
                │
                ▼
    Kiểm tra magic và version được hỗ trợ
                │
                ▼
    Phân tích cấu trúc ClassFile
    constant pool, field, method, attribute...
                │
                ▼
    Kiểm tra hợp lệ và bytecode verification
                │
                ▼
    Linking / initialization khi cần
                │
                ▼
    Thực thi method bytecode bằng JVM
```

Sơ đồ nhằm làm rõ **các trách nhiệm**, không cam kết thứ tự chi tiết mọi thao tác giống hệt trên tất cả JVM hoặc mọi lớp được verify/resolve/initialize hoàn toàn ngay một lúc.

- **Class loader** cung cấp định nghĩa lớp dưới dạng các byte; nguồn có thể là file `.class`, một mục trong JAR, module hoặc cơ chế loader khác.
- **Nhận diện format**: magic number và class-file version giúp runtime xác định định dạng có thể đọc và được phép xử lý.
- **Phân tích cấu trúc**: JVM kiểm tra tổ chức các khối và ràng buộc của thông tin như constant pool, tên class, descriptor và thuộc tính.
- **Bytecode verification**: JVM kiểm tra điều kiện an toàn kiểu/trạng thái stack và tính hợp lệ của lệnh theo quy tắc class file tương ứng.
- **Linking, initialization và thực thi**: runtime chuẩn bị và khởi tạo lớp ở thời điểm thích hợp, rồi thực thi các phương thức cần thiết.

Các lớp có thể được nạp **lười** khi chương trình sử dụng đến. Vì vậy lỗi class format hoặc incompatibility ở một dependency có thể xuất hiện **sau** khi main class đã chạy được một phần. Không được hiểu rằng magic number thay thế vai trò của verifier.

### Các lỗi liên quan ClassFile

| Lỗi/triệu chứng | Ý nghĩa cần kiểm tra |
| --- | --- |
| `ClassFormatError` | Dữ liệu ClassFile có cấu trúc không hợp lệ; xem class bytes và công cụ tạo/biến đổi class |
| `UnsupportedClassVersionError` | JVM không hỗ trợ phiên bản class file yêu cầu, hoặc tổ hợp phiên bản/preview không hợp lệ |
| `VerifyError` | Bytecode không đáp ứng các yêu cầu kiểm tra của verifier |
| `NoClassDefFoundError` | Runtime cần một lớp nhưng không lấy được định nghĩa thích hợp; có thể do dependency, classpath hoặc lỗi khởi tạo trước đó |
| `ClassNotFoundException` | Cơ chế tải lớp theo tên không tìm được lớp trong ngữ cảnh tìm kiếm; phụ thuộc cách gọi |
| `IOException` từ `ClassHeaderReader` | Công cụ đọc file demo không thể mở/đọc đủ byte; chưa phải lỗi JVM khi chạy chương trình |

`UnsupportedClassVersionError` là một dạng liên quan `ClassFormatError`, và `VerifyError` thuộc nhóm `LinkageError`. Trong ứng dụng thực tế, giữ nguyên stack trace và kiểm tra **tên lớp cụ thể** gây lỗi; đừng mặc định lỗi nằm ở lớp được chỉ rõ trong câu lệnh `java`.

## 8. Vì sao một class file mới có thể không chạy trên JVM cũ?

Giả sử code nguồn tương thích về cú pháp, nhưng bạn biên dịch bằng `javac` JDK 21 không đặt release đích và nhận output major **65**. JVM Java 17 chỉ hiểu tới major **61** sẽ từ chối class file đó.

```text
javac mặc định JDK 21
       │
       └── class file 65.0
                │
                └── JVM Java 17 (tối đa major 61) → không hỗ trợ

javac JDK 21 --release 17
       │
       └── class file 61.0
                │
                └── JVM Java 17 → class-file version phù hợp
```

Dòng cuối chỉ nói **phiên bản file được hỗ trợ**, không cam kết ứng dụng sẽ chạy thành công nếu thư viện ngoài, cấu hình, dữ liệu hoặc hành vi runtime có vấn đề.

### Phân biệt bốn trường hợp

1. **Biên dịch lỗi**: `javac` không tạo bản class hợp lệ cho mã nguồn bị lỗi, ví dụ sai cú pháp hoặc dùng API không thuộc `--release` đích.
2. **Class file có major quá mới**: JVM từ chối ở giai đoạn nạp lớp, có thể báo `UnsupportedClassVersionError`.
3. **Major phù hợp nhưng bytes sai cấu trúc**: class file vẫn có thể bị bác với `ClassFormatError` hoặc `VerifyError`.
4. **Major và bytes hợp lệ nhưng dependency thiếu**: lỗi nạp/liên kết lớp khác vẫn có thể xuất hiện.

Để chẩn đoán, dùng:

```bash
java --version
javac --version
javap -verbose Hello
```

Sau đó đọc dòng `major version`/`minor version` trong output `javap` rồi đối chiếu release được hỗ trợ của runtime thực tế.

## 9. Điều không nên suy luận chỉ từ 8 byte header

**Không thể kết luận chương trình an toàn.** Header không kiểm tra signature số, nguồn tải về, package, bytecode độc hại hay ý nghĩa nghiệp vụ.

**Không thể biết toàn bộ API mà chương trình dùng.** Major version có thể nói về mức định dạng class file, nhưng muốn xác định method/field/dependency cụ thể phải xem constant pool, method bytecode, descriptor và những lớp phụ thuộc. `--release` giới hạn API Java chuẩn khi biên dịch nhưng không kiểm tra mọi thư viện bên ngoài.

**Không thể biết JIT có tối ưu gì.** Header thuộc định dạng lưu trữ; JIT là cơ chế runtime xử lý bytecode đã được nạp. `.class` không trực tiếp chứa mã máy JIT sinh ra cho CPU hiện tại.

**Không thể giả định file chỉ có một loại metadata.** `attributes` có thể chứa dữ liệu của compiler/debugger/framework; JVM có quy tắc nhận diện thuộc tính, bỏ qua thuộc tính không nhận ra khi phù hợp, và kiểm tra thuộc tính có ý nghĩa chuẩn.

**Không thể kiểm tra nguyên vẹn JAR bằng magic ClassFile.** JAR là container ZIP; phải mở đúng entry `.class` bên trong và đọc từng header. Cùng một ứng dụng có thể có nhiều class file với major khác nhau do quá trình build hoặc thiết kế multi-release JAR.

## 10. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập A — Tính phiên bản từ byte

Bạn đọc thấy tám byte đầu:

```text
CA FE BA BE 00 00 00 41
```

- Magic là **`0xCAFEBABE`**.
- Minor = **0**.
- Major = **`0x0041 = 65`**, tương ứng class-file version chuẩn Java 21.

Nếu cố mở bằng JVM Java 17, bước kiểm tra phiên bản sẽ thất bại vì Java 17 không hỗ trợ major 65.

### Bài tập B — Suy luận preview marker

Header:

```text
CA FE BA BE FF FF 00 3D
```

- Magic vẫn là `0xCAFEBABE`.
- Minor = `0xFFFF = 65535`.
- Major = `0x003D = 61`.

Đây là cặp giá trị gắn với **class preview version Java 17** theo quy tắc của định dạng. Nó cần điều kiện hỗ trợ preview thích hợp, không thể coi như class ổn định 61.0.

### Bài tập C — Vì sao magic đúng chưa đủ?

Tự tạo một tệp chỉ chứa bốn byte:

```text
CA FE BA BE
```

Nó có magic đúng nhưng **không có đủ byte cho `minor_version` và `major_version`**, chưa kể các thành phần bắt buộc khác. Tệp không tạo thành ClassFile hợp lệ; chương trình `ClassHeaderReader` ở trên sẽ gặp lỗi đọc thiếu dữ liệu.

### Câu hỏi ôn tập

**1. `major_version` là phiên bản của JDK chạy `java` hay của `.class`?**  
Là trường **phiên bản định dạng của class file**. Nó được ghi tại lúc tạo/biến đổi file; JDK runtime là một thông tin riêng.

**2. Vì sao `00 3D` cho kết quả 61?**  
Vì ClassFile lưu số nguyên **big-endian**, `0x003D` ở hệ 16 bằng **61** ở hệ 10.

**3. `minor_version = 0` luôn đúng cho mọi ClassFile lịch sử?**  
**Không.** Với class file Java ổn định hiện đại minor thường 0; các bản cũ có quy tắc lịch sử riêng và preview hiện đại có thể dùng 65535.

**4. Một tệp có magic đúng nhưng bytecode sai có được JVM chạy không?**  
Không thể bảo đảm. JVM còn phải kiểm tra **cấu trúc, kiểu, verifier, phiên bản và các quy tắc liên kết**.

**5. Tại sao không sửa `00 41` thành `00 3D` để chạy Java 21 bytecode trên Java 17?**  
Đổi hai byte chỉ đổi **nhãn phiên bản**, không hạ các cấu trúc/opcode/API đã được mã hóa cho release cao hơn. File có thể không còn hợp lệ hoặc vẫn không chạy được.

**6. `javap -verbose` giúp kiểm tra gì?**  
Đọc thông tin **thực tế của class file**: phiên bản major/minor, constant pool, cấu trúc class/method, descriptor và những thuộc tính mà công cụ hỗ trợ hiển thị.

Khi điều tra một tệp `.class`, hãy kiểm tra theo thứ tự: **4 byte magic `CAFEBABE` → 2 byte minor → 2 byte major → toàn bộ cấu trúc và bytecode → khả năng tương thích runtime/dependency**. Ba trường đầu giúp phát hiện sớm sai định dạng hoặc không tương thích phiên bản; chính các bước đọc và kiểm tra tiếp theo mới xác định ClassFile có thể được JVM nạp và thực thi hay không.