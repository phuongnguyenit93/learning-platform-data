# Chọn giữa mã nguồn và class có sẵn khi cùng tìm thấy

## 1. Tình huống: cùng một kiểu Java, có cả .java và .class

Khi biên dịch `Client.java`, `javac` cần biết kiểu `demo.Greeting` được khai báo thế nào. Có thể dự án chứa cả:

- `source-src/demo/Greeting.java` — phiên bản mã nguồn của kiểu đó;
- `lib/demo/Greeting.class` — phiên bản đã biên dịch trước;
- `client-src/demo/Client.java` — mã đang tham chiếu `demo.Greeting`.

Nếu compiler tìm thấy cả source lẫn class file cho **cùng một kiểu cần tra cứu ngầm**, nó phải quyết định dùng bản nào. Với `javac` JDK 17+:

- `-Xprefer:newer` (mặc định): ưu tiên file có thời điểm sửa đổi mới hơn.
- `-Xprefer:source`: ưu tiên file nguồn khi cả source và class được tìm thấy.
- Khi file nguồn được chọn ngầm, `javac` có thể biên dịch file đó và sinh class file bổ sung. `-implicit:class` hoặc `-implicit:none` kiểm soát **việc phát class file cho nguồn ngầm**, không thay thế quy tắc `-Xprefer`.

Quy tắc này giải thích nhiều sự cố khó đoán: sửa một file nguồn nhưng compiler vẫn dùng binary cũ; lệnh biên dịch một file lại phát thêm class của file khác; một build chạy đúng trên máy A nhưng dùng bản dependency khác trên máy B; hoặc compile thành công nhưng runtime vẫn nạp class cũ.

**Mục tiêu học tập:** xác định các vị trí `javac` tìm kiểu, hiểu đúng điều kiện áp dụng `-Xprefer`, quan sát việc chọn source/class bằng một ví dụ có thể chạy, phân biệt `-implicit` với `-Xprefer` và giải quyết trường hợp output/runtime classpath không nhất quán.

Bài dùng dự án Java trên classpath (unnamed module), JDK 17+ và ví dụ kiểm chứng bằng `javac` JDK 21. Với dự án Java Platform Module System (JPMS), tìm kiểu trong module tuân theo thêm quy tắc module, được nhắc ở phần cuối.

## 2. Trước khi chọn: javac tìm một kiểu ở đâu?

Với lệnh:

```bash
javac -cp lib --source-path source-src -d out client-src/demo/Client.java
```

compiler cần các khai báo từ `Client.java` và từ những kiểu được tham chiếu bởi nó, ví dụ `demo.Greeting`. Để tìm kiểu chưa được cung cấp trực tiếp, nó xem các vị trí thích hợp:

| Nguồn thông tin | Tùy chọn | Được tìm gì? |
| --- | --- | --- |
| **File nguồn được nêu trực tiếp** | `client-src/demo/Client.java` (hoặc danh sách nhiều `.java`) | Các source file mà lệnh yêu cầu compiler xử lý |
| **Source path** | `--source-path source-src` / `-sourcepath source-src` | Các source file phụ thuộc chưa được liệt kê trực tiếp, theo package hierarchy |
| **Classpath** | `-cp lib` / `--class-path lib` | Các class file/JAR được compile sẵn |
| **Platform modules** | Cấu hình hệ thống mặc định hoặc `--system`/`--release` | Các kiểu của nền tảng Java SE tương ứng, theo quy tắc module |
| **Module path** | `--module-path` và các tùy chọn liên quan | Module đã biên dịch; quy tắc tra cứu phụ thuộc module graph |

Ở ví dụ **không dùng module**:

1. Nếu đặt cả `-cp` và `--source-path`, `javac` tìm **class files trên classpath** và **source files trên source path**.
2. Nếu đặt `-cp` mà không có `--source-path`, `javac` có thể tìm **cả `.class` lẫn `.java` trên user classpath**.
3. Nếu không đặt classpath, giá trị mặc định của user classpath là thư mục làm việc hiện tại, trừ khi môi trường như `CLASSPATH` ảnh hưởng; hãy ghi rõ classpath khi cần tái hiện.
4. File source được tìm ngầm cần nằm theo cấu trúc package thích hợp, chẳng hạn kiểu `demo.Greeting` tương ứng với `demo/Greeting.java` dưới một source-path root.

**`-d out` chỉ chọn nơi ghi output.** Với bài toán classpath thông thường, nó **không tự bổ sung `out` vào compile classpath**. Nếu muốn compiler dùng những class file đã có dưới `out` làm dependency, phải khai báo `-cp out` hoặc một classpath thích hợp.

Có hai kiểu “tìm thấy” rất khác nhau: tìm được hai **phiên bản của cùng một type**, một là source và một là binary; hoặc tìm được hai binary **trùng tên** trên hai classpath entries. `-Xprefer` xử lý trường hợp **source và class cùng được tìm thấy**, không phải nút chọn giữa hai JAR khác nhau chứa cùng một class.

## 3. Chính xác khi nào -Xprefer áp dụng?

`javac` cho phép:

```text
-Xprefer:source
-Xprefer:newer
```

| Chế độ | Khi cùng tìm được source và class của một kiểu được tìm ngầm | Nếu chỉ có một dạng |
| --- | --- | --- |
| `-Xprefer:newer` | Chọn file có thời điểm sửa đổi mới hơn; đây là mặc định | Dùng dạng tìm được |
| `-Xprefer:source` | Chọn source file | Dùng dạng tìm được |

Tài liệu Oracle diễn đạt rõ phạm vi này là **implicitly compiled classes**: compiler gặp một kiểu cần dùng mà file nguồn của kiểu đó **không nằm trong danh sách source files truyền tường minh**.

Ví dụ hai lệnh khác nhau về căn bản:

```bash
# Greeting.java được yêu cầu biên dịch tường minh
javac -d out client-src/demo/Client.java source-src/demo/Greeting.java
```

```bash
# Chỉ Client.java là nguồn tường minh; Greeting được tìm qua sourcepath/classpath
javac -cp lib --source-path source-src -Xprefer:source -d out client-src/demo/Client.java
```

Ở lệnh thứ nhất, `Greeting.java` là **đầu vào source được yêu cầu trực tiếp**. Không cần so sánh timestamp với một `Greeting.class` để quyết định có xử lý file nguồn đó hay không.

Ở lệnh thứ hai, compiler chỉ bắt đầu từ `Client.java` rồi tra `Greeting` theo đường dẫn tìm kiếm. Nếu cả hai dạng tồn tại, `-Xprefer` mới điều khiển việc chọn bản được đọc.

**Đừng diễn giải `-Xprefer:source` là “luôn biên dịch lại mọi file nguồn trong dự án”.** Nó không quét toàn repository và không tác động đến một kiểu mà compiler không cần tra cứu hoặc không tìm thấy source. Ngược lại, khi source được chọn ngầm, compiler có thể tạo thêm class files mà bạn không liệt kê trong command line.

## 4. Ví dụ runnable: cùng tên kiểu, hai phiên bản khác nội dung

Tạo một thư mục mới `prefer-demo` với cây nguồn sau:

```text
prefer-demo/
├── binary-src/
│   └── demo/
│       └── Greeting.java
├── source-src/
│   └── demo/
│       └── Greeting.java
└── client-src/
    └── demo/
        └── Client.java
```

Hai `Greeting.java` có **cùng tên đầy đủ `demo.Greeting`**, nhưng nội dung khác nhau. Đây là cấu trúc để thử nghiệm chọn nguồn/binary; không đưa cả hai file vào cùng một lệnh compile.

### 4.1. Phiên bản dùng để tạo binary có sẵn

File `binary-src/demo/Greeting.java`:

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "BINARY";
    }
}
```

### 4.2. Phiên bản source có sẵn cho compiler

File `source-src/demo/Greeting.java`:

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "SOURCE";
    }
}
```

Hai file đều khai báo đúng package `demo` và public class `Greeting`, nhưng khác phần thân method `text()`. Vì cùng chữ ký method, `Client` có thể biên dịch hợp lệ với cả hai; sự khác nhau sẽ xuất hiện khi chạy để dễ quan sát.

### 4.3. Client dùng Greeting nhưng không định nghĩa lại nó

File `client-src/demo/Client.java`:

```java
package demo;

public final class Client {
    private Client() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.text());
    }
}
```

`Client` và `Greeting` cùng package nên không cần `import demo.Greeting`. `Client` chỉ gọi method công khai có ở cả hai bản `Greeting`.

### 4.4. Biên dịch bản BINARY vào thư mục lib

Đứng tại `prefer-demo`:

```bash
javac --release 17 -d lib binary-src/demo/Greeting.java
```

Kết quả:

```text
lib/
└── demo/
    └── Greeting.class
```

File class này có method `text()` trả về `"BINARY"`. Từ thời điểm này, ta có một binary dependency hợp lệ. `lib` là **compile/runtime classpath root**, không phải tên package.

Không đưa `binary-src` vào source path cho các lệnh thử nghiệm tiếp theo; source candidate mong muốn nằm ở `source-src`.

## 5. Thử nghiệm 1: ép javac ưu tiên source

Lệnh sau chỉ liệt kê **Client.java** là source đầu vào tường minh. Compiler sẽ phải tìm `demo.Greeting`:

```bash
javac --release 17 -cp lib --source-path source-src -Xprefer:source -implicit:class -d out client-src/demo/Client.java
```

Giải thích từng phần:

- `-cp lib` cho compiler thấy `lib/demo/Greeting.class`.
- `--source-path source-src` cho compiler thấy `source-src/demo/Greeting.java`.
- `-Xprefer:source` yêu cầu lấy khai báo từ **source** nếu cả hai cùng được tìm thấy.
- `-implicit:class` yêu cầu sinh class file cho những source được đọc **ngầm**.
- `-d out` để kết quả lần compile này tách khỏi `lib`.
- `--release 17` giữ ví dụ theo Java 17; nó không thay đổi logic chọn file của `-Xprefer`.

Sau khi biên dịch thành công, `out` có:

```text
out/
└── demo/
    ├── Client.class
    └── Greeting.class
```

`Greeting.class` trong `out` được compiler phát từ **source-src/demo/Greeting.java**, không phải một bản sao tự động của `lib/demo/Greeting.class`.

Chạy trên Linux/macOS:

```bash
java -cp "out:lib" demo.Client
```

Hoặc Windows PowerShell:

```powershell
java -cp 'out;lib' demo.Client
```

**Stdout chính xác:**

```text
SOURCE
```

Lý do: compiler đã chọn source và tạo `out/demo/Greeting.class`; runtime classpath liệt kê `out` **trước** `lib` nên JVM nạp phiên bản vừa biên dịch. Nếu đảo thành `lib:out` trên Linux/macOS (hoặc `lib;out` trên Windows), chương trình có thể in `BINARY` vì runtime classpath chọn bản ở `lib` trước. **Quy tắc chọn của javac lúc compile không đồng nghĩa với thứ tự nạp class lúc runtime.**

Thí nghiệm này không phụ thuộc timestamp: `-Xprefer:source` ưu tiên source dù file class mới hơn.

## 6. Thử nghiệm 2: mặc định chọn file mới hơn

Bỏ `-Xprefer:source` thì `javac` dùng chế độ tương đương `-Xprefer:newer`. Khi cả source và class được tìm thấy, compiler so thời điểm sửa đổi của hai file. Muốn dự đoán kết quả, ta phải **cố định timestamp trước khi thử**, thay vì dựa vào việc vừa tạo file nào trước.

Với Linux/macOS có `touch`, ở thư mục `prefer-demo`:

```bash
touch -t 202001010000 source-src/demo/Greeting.java
touch -t 202101010000 lib/demo/Greeting.class
```

Hai lệnh này chỉ điều chỉnh mtime để class file mới hơn source file. Chúng không sửa nội dung source hay binary. Với Windows PowerShell:

```powershell
(Get-Item 'source-src/demo/Greeting.java').LastWriteTimeUtc = [datetime]'2020-01-01T00:00:00Z'
(Get-Item 'lib/demo/Greeting.class').LastWriteTimeUtc = [datetime]'2021-01-01T00:00:00Z'
```

Sau đó dùng **thư mục output khác**, tránh class file tồn từ thử nghiệm trước:

```bash
javac --release 17 -cp lib --source-path source-src -Xprefer:newer -d out-newer client-src/demo/Client.java
```

Với mtime vừa đặt, `lib/demo/Greeting.class` mới hơn `source-src/demo/Greeting.java`. Compiler đọc class file; nó chỉ cần phát `out-newer/demo/Client.class` và không cần compile `Greeting.java` vào `out-newer`.

Chạy Linux/macOS:

```bash
java -cp "out-newer:lib" demo.Client
```

Hoặc Windows PowerShell:

```powershell
java -cp 'out-newer;lib' demo.Client
```

**Stdout chính xác với bộ file và mtime đã cố định:**

```text
BINARY
```

`Greeting.class` chỉ nằm ở `lib` trong bài thử này, nên JVM nạp bản trả về `BINARY`. Nếu bỏ `-Xprefer:newer` trong lệnh compile thì nó vẫn là **chế độ mặc định** của `javac`.

Thay đổi mtime theo hướng source mới hơn class sẽ đổi quyết định của chế độ `newer` khi các điều kiện khác giữ nguyên. Đây là lý do copy source, restore artifact từ cache, đổi filesystem hoặc giải nén file có timestamp khác có thể khiến `javac` chọn đầu vào khác dù tên các file giữ nguyên.

**Mốc thời gian không phải version control.** Một class file có mtime mới không chắc chứa nội dung mới hơn về mặt tính năng. Nếu cần tái hiện chắc chắn, ghi hashes, source/build version và lựa chọn `-Xprefer`; chỉ dựa vào mtime là rủi ro.

## 7. Thử nghiệm 3: source được đọc, nhưng không phát class mới

Chạy:

```bash
javac --release 17 -cp lib --source-path source-src -Xprefer:source -implicit:none -d out-none client-src/demo/Client.java
```

`-Xprefer:source` vẫn cho compiler dùng `Greeting.java` để kiểm tra các tham chiếu của `Client.java`. Tuy nhiên, `-implicit:none` **không sinh `Greeting.class` từ nguồn được tìm ngầm**. Trong ví dụ này, output chỉ cần:

```text
out-none/
└── demo/
    └── Client.class
```

Chạy trên Linux/macOS:

```bash
java -cp "out-none:lib" demo.Client
```

Hoặc Windows PowerShell:

```powershell
java -cp 'out-none;lib' demo.Client
```

**Stdout:**

```text
BINARY
```

Vì `out-none` không chứa `Greeting.class`, JVM dùng `lib/demo/Greeting.class`, trả `BINARY`. Đây là một tình huống quan trọng: **javac đã kiểm tra source nhưng runtime nạp binary khác**.

Trong bài thử, hai phiên bản `Greeting` có cùng chữ ký `text():String`, nên lời gọi vẫn liên kết được. Nếu source có thêm method mới mà binary thiếu, client có thể biên dịch thành công theo source rồi lỗi `NoSuchMethodError` khi chạy với binary cũ. Vì vậy không được coi việc biên dịch thành công với `-implicit:none` là bằng chứng rằng runtime dependency đã tương thích.

**`-implicit:none` không có nghĩa “đọc class thay source”.** Nó chỉ tắt phát class file cho source phụ thuộc được tìm ngầm. Nếu file nguồn được **liệt kê trực tiếp** trên command line, nó vẫn là một source compilation unit và không bị coi là nguồn ngầm chỉ vì cờ này.

## 8. -Xprefer và -implicit giải quyết hai câu hỏi khác nhau

| Câu hỏi | Tùy chọn | Hệ quả |
| --- | --- | --- |
| Khi có cả `Greeting.java` và `Greeting.class`, compiler nên **đọc loại nào**? | `-Xprefer:source` hoặc `-Xprefer:newer` | Chọn source hoặc binary để hiểu khai báo kiểu |
| Nếu compiler **đã chọn một source file được tìm ngầm**, có phát `.class` cho nó không? | `-implicit:class` hoặc `-implicit:none` | Phát thêm class file hoặc chỉ dùng source làm thông tin kiểu |

Một vài trường hợp đáng nhớ:

| Trạng thái ứng viên | Cờ chọn | Cờ implicit | Kết quả |
| --- | --- | --- | --- |
| Chỉ tìm được class | Bất kỳ | Bất kỳ | Dùng class; không compile source không tồn tại |
| Chỉ tìm được source | Bất kỳ | `-implicit:class` | Đọc source và phát class cho nguồn ngầm |
| Chỉ tìm được source | Bất kỳ | `-implicit:none` | Đọc source; không phát class cho nguồn ngầm |
| Tìm được cả hai, source mới hơn | `-Xprefer:newer` | `-implicit:class` | Chọn source; phát class |
| Tìm được cả hai, class mới hơn | `-Xprefer:newer` | `-implicit:class` | Chọn class; không phát class từ source đó |
| Tìm được cả hai, class mới hơn | `-Xprefer:source` | `-implicit:class` | Chọn source; phát class |
| Tìm được cả hai | `-Xprefer:source` | `-implicit:none` | Chọn source; không phát class cho source ngầm |

Khi không ghi `-implicit`, mặc định `javac` sinh class file cho source được tìm ngầm. Nếu annotation processing đang chạy và nguồn được phát hiện muộn, compiler có thể cảnh báo việc một file được compile mà không đi qua annotation processing theo cách thông thường. Để tránh phụ thuộc vào hành vi ngầm trong build có processors, hãy xem xét **liệt kê tường minh** mọi source cần được annotation-process và ghi rõ chế độ `-implicit`.

`-Xprefer:source` còn hữu ích nếu annotation processor cần nhìn những annotation có retention `SOURCE`; bản class file đã biên dịch không lưu lại annotation dạng đó. Dù vậy, việc processor có được chạy và có thấy annotation hay không còn phụ thuộc cách xử lý nguồn, processor path và compilation setup, không chỉ một cờ `-Xprefer`.

## 9. Quan sát javac đã chọn file nào

Khi cần chẩn đoán một lần build không như dự kiến, **đừng đoán từ stdout của chương trình**. Runtime classpath có thể che khuất quyết định compile. Có ba cách kiểm chứng nên kết hợp:

### 9.1. Dùng -verbose

```bash
javac --release 17 -verbose -cp lib --source-path source-src -Xprefer:source -implicit:class -d out client-src/demo/Client.java
```

`javac -verbose` báo các thông tin như file source được parse, các kiểu được load và class files được viết. Trong log, tìm đúng đường dẫn `source-src/demo/Greeting.java` hoặc `lib/demo/Greeting.class` và các file output. **Câu chữ/định dạng của log phụ thuộc phiên bản JDK**, nên không viết test dựa trên một dòng thông báo nguyên văn của bản compiler hiện tại.

### 9.2. Xem chính class file được tạo

Sau compile ở `out`:

```bash
javap -c -classpath out demo.Greeting
```

Vì hai phiên bản có constant string `SOURCE` và `BINARY` khác nhau, output `javap -c` có thể giúp xác định implementation nào đã tạo artifact. Cũng có thể chạy trực tiếp `java -cp out demo.Client` nếu mọi dependencies cần thiết có trong `out`.

Nếu `out` không có `Greeting.class`, `javap -classpath out demo.Greeting` không tìm được kiểu đó. Đừng tự thêm `lib` vào classpath của `javap` mà không ghi rõ: nếu dùng `-classpath out:lib`, `javap` có thể đọc file binary từ `lib`, gây nhầm tưởng đó là artifact của `out`.

### 9.3. Kiểm tra từng classpath root theo thứ tự

Một chương trình có thể biên dịch theo source mà chạy từ JAR cũ vì runtime classpath đặt JAR đó trước thư mục output mới. Ghi lại:

- Compile classpath, source path và toàn bộ thứ tự đường dẫn;
- Output dir của compile và danh sách file `.class` thực tế;
- Runtime classpath, module path và các dependency;
- Compiler version, `-Xprefer`, `-implicit` và mtime/hash của hai ứng viên.

Nếu cần biết class được JVM nạp từ đâu khi chạy, tùy phiên bản Java có thể dùng logging class loading như `-Xlog:class+load=info` trên HotSpot. Đây là **công cụ runtime**, không phải tùy chọn `javac`; cần đọc log và xác định đường dẫn nguồn class, không dựa chỉ vào tên class.

## 10. Những trường hợp dễ nhầm với chọn source/class

### 10.1. Hai JAR chứa cùng một tên class

Nếu `lib/old.jar` và `lib/new.jar` cùng chứa `demo.Greeting`, đó là vấn đề classpath có **hai binary ứng viên**. `-Xprefer:source` không chọn giữa hai JAR. Hãy xem thứ tự classpath, classloader, module configuration và loại bỏ dependency trùng.

### 10.2. Source không nằm trong đường dẫn mà javac tìm

Nếu `Greeting.java` tồn tại trong repository nhưng không nằm trên `--source-path` và cũng không được liệt kê tường minh, compiler không nhất thiết tìm thấy nó. `-Xprefer:source` **không buộc compiler quét mọi thư mục trên máy**.

Ví dụ:

```bash
javac --release 17 -cp lib -Xprefer:source -d out-only-binary client-src/demo/Client.java
```

Trong ví dụ, `lib` chỉ chứa class file; không đặt source path trỏ đến `source-src`. Compiler sẽ sử dụng `Greeting.class` từ `lib` nếu không có source ứng viên khác trong đường dẫn tìm kiếm. Cờ prefer không tạo ra ứng viên nguồn từ một thư mục không được cấu hình.

### 10.3. Một file Java đã được nêu trực tiếp

Lệnh này yêu cầu compile `Greeting.java` tường minh, không phụ thuộc vào timestamp của `lib/demo/Greeting.class`:

```bash
javac --release 17 -cp lib -d out-explicit client-src/demo/Client.java source-src/demo/Greeting.java
```

Sau đó dùng output mới trước `lib` trên runtime classpath để chạy đúng bản đã compile. Nếu truyền cùng lúc **hai file nguồn** đều khai báo public `demo.Greeting`, đây là lỗi định nghĩa trùng, không phải bài toán `-Xprefer`.

### 10.4. Compiler báo lỗi vì nguồn mới nhưng binary cũ

Nếu `source-src/demo/Greeting.java` có API khác binary, việc chuyển từ `newer` sang `source` có thể làm client được kiểm tra theo một API khác, dẫn tới lỗi compile hoặc runtime linkage. Điều này không mâu thuẫn quy tắc Java; nó cho thấy build đang pha trộn hai phiên bản dependency. Hãy khóa version, làm clean build và bảo đảm binary tương ứng với nguồn được chọn.

### 10.5. -d out không phải classpath

Lệnh `javac -d out Client.java` chỉ chỉ định output dir. Muốn sử dụng class đã biên dịch từ lượt trước trong `out`, đặt `-cp out` (cùng các dependencies khác) ở lần biên dịch tiếp theo. Đừng coi việc một file có mặt trong thư mục output là bảo đảm compiler tự đọc nó từ classpath.

### 10.6. Chọn source theo mtime không đồng nghĩa chọn nội dung đúng

Git checkout, giải nén artifact, đồng bộ đồng hồ máy và caching có thể làm mtime thay đổi dù byte nội dung không đổi. `-Xprefer:newer` là một chiến lược dựa trên mtime, **không phải** thuật toán so sánh hash hoặc đọc semver. Với build quan trọng, quản lý dependency và source inputs bằng hệ thống build cùng checksums, tránh dựa vào thứ tự sửa file tình cờ.

## 11. Giới hạn với Java modules (JPMS)

Các thí nghiệm trên dùng source/class tìm theo package trong **unnamed module**. Khi có `module-info.java`, cơ chế xác định module và quyền đọc/export package được áp dụng trước khi compiler tìm các kiểu liên quan:

- Các module trên `--module-path` thường cung cấp **class files đã biên dịch**; compiler không tự tìm các source files thay thế chỉ vì ở đâu đó có file cùng tên.
- Nguồn cho một hoặc nhiều module đang biên dịch có thể được cung cấp qua file tường minh, `--source-path` (một module) hoặc `--module-source-path` (nhiều module), theo chế độ và cấu trúc dự án.
- Một số trường hợp tra cứu trong **module đang được compile** còn xét output module theo quy tắc được mô tả trong tài liệu `javac`, khác cấu hình classpath đơn giản của bài học.
- `-Xprefer` chỉ có ý nghĩa ở những điểm tìm kiếm cho ra cả ứng viên source và class; không nên dùng nó để giải quyết split-package, module readability hay dependency module graph sai.

Khi làm việc với JPMS, hãy đọc phần **Searching for Module, Package and Type Declarations** trong tài liệu `javac` đúng phiên bản, cùng `--module-path`, `--module-source-path`, `--patch-module` nếu có. Bài này nhấn mạnh trường hợp classpath vì nó cho thấy trực tiếp hành vi `-Xprefer` và `-implicit`.

## 12. Quy trình thực tế để chọn và kiểm tra nguồn đúng

1. **Xác định kiểu cần resolve** và xem đó là nguồn liệt kê trực tiếp hay phụ thuộc được tra cứu ngầm.
2. **Ghi compile input:** JDK version, cwd, classpath/sourcepath có thứ tự, các file source, binary dependencies, `-Xprefer` và `-implicit`.
3. **Tìm cả hai ứng viên:** source nằm dưới đúng source-path root? Class file/JAR có đúng package và tên binary? Có trùng lớp ở root khác không?
4. **Xác định chính sách:** để mặc định `newer` nếu chấp nhận mtime; chọn `-Xprefer:source` khi cố ý ưu tiên source và hiểu hậu quả.
5. **Quyết định phát class:** dùng `-implicit:class` nếu muốn binary đồng bộ cho nguồn ngầm; dùng `-implicit:none` khi có lý do rõ ràng và quản lý runtime dependency tương ứng.
6. **Biên dịch vào output cô lập**, tránh tồn dư class từ thử nghiệm khác.
7. **Kiểm chứng quyết định compile** bằng `-verbose`, danh sách output và `javap`; không kết luận chỉ từ log runtime.
8. **Kiểm tra runtime classpath** theo đúng thứ tự và chạy chương trình/test.
9. **Muốn build ổn định dài hạn**, ưu tiên nhóm nguồn tường minh, dependency đã khóa và build tool quản lý từng source set, thay vì tận dụng mtime để giải quyết các phiên bản API khác nhau.

## 13. Bài tập tự kiểm tra và đáp án

**Câu 1.** `source-src/demo/Greeting.java` mới hơn `lib/demo/Greeting.class`. Compiler tìm được cả hai khi xử lý `Client.java`, không đặt `-Xprefer`. Nó ưu tiên gì?

**Đáp án:** `-Xprefer:newer` là mặc định, nên chọn **source** vì mtime nguồn mới hơn, rồi có thể sinh class file cho nó theo `-implicit`.

**Câu 2.** Class mới hơn source nhưng muốn chắc chắn compiler đọc source để annotation processor thấy annotation có retention `SOURCE`. Nên chọn gì?

**Đáp án:** `-Xprefer:source` cho tình huống tra cứu ngầm có cả source/class. Đồng thời kiểm tra cấu hình processors và cách các source files được cung cấp, vì việc chọn source không thay thế việc cấu hình annotation processing.

**Câu 3.** `-Xprefer:source -implicit:none` có nghĩa “compiler sẽ không dùng source” đúng không?

**Đáp án:** Sai. Compiler vẫn có thể đọc source để kiểm tra kiểu. `-implicit:none` chỉ ngăn phát class file cho source được tìm **ngầm**.

**Câu 4.** `javac -cp lib -Xprefer:source Client.java` có tự tìm `source-src/demo/Greeting.java` không?

**Đáp án:** Không nếu thư mục `source-src` không nằm trong đường dẫn source lookup thích hợp. `-Xprefer` chỉ chọn trong những ứng viên mà compiler thực sự tìm được.

**Câu 5.** Compile chọn source và sinh `out/demo/Greeting.class`, nhưng chạy với classpath `lib:out` lại in `BINARY`. Vì sao?

**Đáp án:** Runtime classpath liệt kê `lib` trước. JVM nạp bản class file từ `lib`; đây là quy tắc tìm class lúc chạy, tách biệt với quyết định đọc source/class của `javac` khi compile.

**Câu 6.** Có hai JAR chứa cùng `demo.Greeting`. `-Xprefer:source` có chọn JAR mới hơn không?

**Đáp án:** Không. Đây là hai binary cùng tên, không phải cặp source/class. Cần kiểm tra classpath order, dependency resolution và module/classloader configuration.

**Câu 7.** Vì sao build dùng `-Xprefer:newer` vẫn có thể không tái hiện dù source commit và compiler version giống nhau?

**Đáp án:** Mtime của source/class, classpath/sourcepath và binary dependencies có thể khác. Các đầu vào đó phải được ghi lại hoặc quản lý bằng build có kiểm soát.

## 14. Tài liệu chuẩn

- **JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — các mục `-Xprefer`, `-implicit`, `--source-path`, `--class-path`, `-verbose` và **Searching for Module, Package and Type Declarations**.
- **JDK 21 — The java Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html — classpath/runtime và cách chạy class.
- **JDK 21 — The javap Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html — xem output class file, methods và bytecode.
- **JLS Java SE 21:** https://docs.oracle.com/javase/specs/jls/se21/html/ — ngữ nghĩa type declaration, import, tên kiểu và binary compatibility.
- **JVMS Java SE 21:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — định nghĩa class file, symbolic references và class loading/linking.

Điểm cần nhớ: **`-Xprefer` chọn giữa source và class khi compiler tra cứu ngầm một kiểu và tìm thấy cả hai; `-implicit` quyết định có phát class từ source được tìm ngầm hay không; runtime classpath lại quyết định JVM nạp class file nào khi chạy.** Muốn dự đoán đúng kết quả, phải xét cả ba tầng này.