# Chạy lớp, JAR, module và tệp nguồn: khác nhau ở cách khởi động JVM

Một chương trình Java có thể được khởi chạy qua **tên lớp**, **JAR có điểm vào**, **module có tên**, hoặc trực tiếp bằng **tệp mã nguồn `.java`**. Bốn cách đều nhằm tìm được mã cần thực thi và gọi điểm vào của chương trình, nhưng khác nhau ở **đối tượng mà Java launcher nhận vào**, **cách tìm lớp và phụ thuộc**, **cách chọn `main`**, và việc **có cần biên dịch trước hay không**.

Ở đây, “khởi chạy JVM” nghĩa là chạy lệnh `java` trong JDK/runtime tương thích. Chúng ta khảo sát bốn chế độ với cú pháp được hỗ trợ trên **Java 17 trở lên**, tập trung vào vòng đời từ câu lệnh khởi chạy tới `main`. Để giữ ví dụ chạy được nhất quán, phương thức vào chương trình dùng chữ ký quen thuộc của Java 17: `public static void main(String[] args)`.

## 1. Bức tranh chung: launcher chọn cách tìm chương trình

```text
                    Người dùng gọi lệnh java
                               │
          ┌────────────────────┼─────────────────────┐
          │                    │                     │
   Tên lớp trên           JAR có manifest        Module có tên
     classpath                Main-Class            trong module path
   java -cp ...             java -jar ...             java -m ...
          │                    │                     │
          └─────────────┬──────┴─────────────────────┘
                        │
                 Tìm và nạp main class
                        │
                        ▼
             JVM liên kết/khởi tạo lớp
                        │
                        ▼
                   Gọi main(args)
                        │
                        ▼
                 Thực thi bytecode
             (interpreter/JIT tùy JVM)

  Đường thứ tư: java File.java → biên dịch mã nguồn trong bộ nhớ
                     → nạp main class → chạy như trên
```

Mô hình trên mô tả **chọn chế độ launch và chuyển quyền điều khiển vào ứng dụng**, không có nghĩa tất cả dependency được nạp cùng lúc. JVM còn thực hiện khởi tạo runtime, phân giải module khi dùng module, nạp/liên kết lớp khi cần, quản lý luồng và bộ nhớ, rồi thực thi bytecode theo cơ chế của bản JVM. Việc gọi `main` cũng không đồng nghĩa toàn bộ vòng đời JVM kết thúc ngay khi phương thức này trả về: các luồng còn sống và các điều kiện kết thúc tiến trình vẫn ảnh hưởng thời điểm JVM thoát.

### Bảng so sánh nhanh

| Chế độ | Câu lệnh mẫu | Đầu vào trực tiếp | Cách xác định điểm vào | Cần biên dịch trước? |
| --- | --- | --- | --- | --- |
| **Class** | `java -cp out demo.LaunchDemo` | Tên lớp đầy đủ | Tên lớp trên classpath và `main` của lớp đó | Thông thường có |
| **Executable JAR** | `java -jar app.jar` | Đường dẫn JAR | Thuộc tính `Main-Class` trong manifest | Có; thường còn cần đóng gói JAR |
| **Named module** | `java --module-path mods -m com.example.launch/demo.LaunchDemo` | Tên module và (tùy chọn) lớp main | Module được resolve, sau đó chọn main class chỉ định hoặc cấu hình sẵn | Có; module descriptor và class file |
| **Source file** | `java src/demo/LaunchDemo.java` | Đường dẫn tệp `.java` | Java launcher biên dịch mã nguồn trong bộ nhớ, rồi thực thi lớp chính trong tệp | **Không cần chạy `javac` riêng** |

Một JAR thông thường chứa các tệp `.class` và tài nguyên; **JAR không phải mã máy**. “Chạy JAR” là một cách phân phối/chọn điểm vào. “Chạy module” là cách tổ chức và phân giải module theo Java Platform Module System (JPMS), không phải một kiểu CPU mới.

## 2. Chuẩn bị một chương trình dùng chung cho cả bốn cách

Tạo thư mục dự án và tệp mã nguồn sau (đường dẫn tính từ thư mục dự án):

```text
project/
└── src/
    └── demo/
        └── LaunchDemo.java
```

Nội dung **`src/demo/LaunchDemo.java`**:

```java
package demo;

public class LaunchDemo {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "không truyền" : args[0];
        System.out.println("Chế độ: " + mode);
    }
}
```

Lớp nằm trong package `demo`, vì thế **tên đầy đủ của lớp là `demo.LaunchDemo`**. Chương trình chỉ in tham số đầu tiên truyền cho `main`; điều này giúp phân biệt lệnh `java` xử lý **launcher options** hay **application arguments**. Các ví dụ dưới đây đều chạy từ thư mục `project/`, sử dụng JDK 17+, với tập tin `LaunchDemo.java` được lưu UTF-8.

```bash
java --version
javac --version
```

Nếu máy có nhiều JDK, hãy kiểm tra hai lệnh dùng đúng phiên bản mong muốn trước khi đọc lỗi của chương trình.

## 3. Chế độ 1 — Chạy một lớp bằng tên đầy đủ

### Biên dịch

```bash
mkdir out
javac -encoding UTF-8 -d out src/demo/LaunchDemo.java
```

Lệnh `javac` kiểm tra mã nguồn và tạo:

```text
out/
└── demo/
    └── LaunchDemo.class
```

Tham số `-d out` xác định nơi đặt class file; cấu trúc bên dưới gắn với tên package. Trong trường hợp này, thư mục **`out` mới là classpath root**, còn `out/demo` chỉ là thư mục package của lớp.

### Chạy

```bash
java -cp out demo.LaunchDemo class
```

**Standard output:**

```text
Chế độ: class
```

Phân tích lệnh:

- `java`: khởi động Java launcher và runtime.
- `-cp out` (viết đầy đủ `-classpath out` hoặc `--class-path out`): cung cấp nơi tìm các lớp/tài nguyên thuộc **classpath**.
- `demo.LaunchDemo`: **binary name** của main class có package, không phải đường dẫn hệ thống.
- `class`: tham số ứng dụng thứ nhất, nhận tại `args[0]`, không phải tên lớp hoặc một tùy chọn JVM.

Các lớp ứng dụng trên classpath thuộc **unnamed module**. Classpath không cần khai báo `module-info.java` và không có ranh giới `requires`/`exports` của named module theo JPMS.

**Vì sao `java LaunchDemo` có thể không chạy?** Lớp mẫu khai báo `package demo;`, nên tên cần chạy là `demo.LaunchDemo`. Cũng không dùng `java out/demo/LaunchDemo.class` ở chế độ này: launcher đang đòi **tên lớp**, không phải đường dẫn tệp `.class`.

### Khi nào dùng?

Chạy trực tiếp theo tên lớp tiện cho bài học, thử nhanh chương trình đã biên dịch, hoặc khi công cụ build/IDE quản lý classpath và biết chính xác main class. Với chương trình nhiều thư viện, classpath cần bao gồm đầy đủ thư mục/JAR phụ thuộc tại runtime. Trên nhiều hệ điều hành, dấu phân tách các mục classpath khác nhau: thường là `;` ở Windows và `:` ở Linux/macOS. Nếu dùng các đường dẫn phức tạp, đặt chuỗi classpath trong dấu nháy phù hợp shell.

## 4. Chế độ 2 — Chạy JAR có `Main-Class`

Từ **class file đã tạo ở bước 3**, đóng gói JAR:

```bash
jar --create --file app.jar --main-class demo.LaunchDemo -C out .
```

Lệnh này tạo `app.jar` chứa lớp `demo/LaunchDemo.class` và manifest có **`Main-Class: demo.LaunchDemo`**. Dấu `-C out .` có nghĩa là đổi vào thư mục `out` trong lúc thêm nội dung, để bên trong JAR là đường dẫn package `demo/LaunchDemo.class`, không thêm tiền tố `out/`.

Kiểm tra các mục trong JAR:

```bash
jar --list --file app.jar
```

Danh sách thường bao gồm `META-INF/MANIFEST.MF` và `demo/LaunchDemo.class`. Sự tồn tại của class file **không tự động làm một JAR chạy được bằng `-jar`**: manifest phải định danh main class phù hợp.

Khởi chạy:

```bash
java -jar app.jar jar
```

**Standard output:**

```text
Chế độ: jar
```

Ở chế độ này, launcher mở JAR và tìm `Main-Class` trong manifest để biết phải khởi chạy lớp nào. Nhờ đó người dùng không cần nhớ tên `demo.LaunchDemo`. `jar` đứng sau đường dẫn JAR nên trở thành `args[0]`.

### Classpath khi dùng `-jar`

Một điểm đặc biệt: với `java -jar app.jar`, **JAR được chỉ định là nguồn tìm lớp ứng dụng chính** và các thiết lập classpath bên ngoài từ `-cp`/`CLASSPATH` không được dùng như ở chế độ khởi chạy tên lớp. Có thể khai báo các JAR phụ thuộc thông qua manifest `Class-Path` hoặc dùng chiến lược đóng gói/phân phối tương ứng. Đừng cho rằng thêm `-cp libs/...` vào câu lệnh `java -jar` sẽ nạp dependency như khi gọi `java -cp`.

Ngược lại, một JAR **không có `Main-Class`** vẫn có thể được dùng trên classpath:

```bash
java -cp app.jar demo.LaunchDemo classpath-jar
```

**Standard output:**

```text
Chế độ: classpath-jar
```

Lần này bạn chủ động chọn **tên lớp**, dùng JAR làm một mục classpath; manifest main class không cần thiết cho lời gọi kiểu `-cp`.

### Khi nào dùng?

Executable JAR phù hợp để phân phối ứng dụng có entry point rõ ràng. Tuy nhiên JAR **không mặc nhiên chứa tất cả thư viện ngoài**. Một “fat JAR” do công cụ build tạo có thể mang cấu trúc riêng hoặc launcher chuyên biệt; cần xem hướng dẫn của đúng công cụ, không suy diễn từ ví dụ JAR thuần ở đây.

## 5. Chế độ 3 — Chạy named module bằng `--module-path` và `-m`

**Java Platform Module System (JPMS)** xuất hiện từ Java 9. Named module có tên và descriptor `module-info.java`; runtime có thể dùng thông tin phụ thuộc (`requires`) và mức độ công khai giữa các module (`exports`, `opens`) khi phân giải và truy cập thành phần. Đây là khác biệt trọng yếu so với classpath.

### Thêm descriptor

Tạo tệp **`src/module-info.java`** bên cạnh cây package `src/demo/`:

```java
module com.example.launch {
}
```

Cây mã nguồn:

```text
project/
└── src/
    ├── module-info.java
    └── demo/
        └── LaunchDemo.java
```

Module này dùng `java.base` mặc định nên không cần ghi `requires java.base;`. Cũng **không cần `exports demo;` chỉ để Java launcher khởi chạy main class của chính module**. `exports` dùng để điều khiển các package được module khác truy cập; không phải một chỉ thị chọn main class.

### Biên dịch thành exploded module

```bash
mkdir mods
mkdir mods/com.example.launch
javac -encoding UTF-8 -d mods/com.example.launch src/module-info.java src/demo/LaunchDemo.java
```

Sản phẩm:

```text
mods/
└── com.example.launch/
    ├── module-info.class
    └── demo/
        └── LaunchDemo.class
```

Thư mục `mods/com.example.launch` là một **exploded module** (module đã biên dịch ở dạng thư mục); `mods` là đường dẫn chứa các module.

### Chạy module và chỉ rõ lớp chính

```bash
java --module-path mods -m com.example.launch/demo.LaunchDemo module
```

**Standard output:**

```text
Chế độ: module
```

Giải thích:

- `--module-path mods` (viết gọn `-p mods`) cung cấp nơi JVM tìm các **observable modules** cần dùng.
- `-m` (tương đương `--module`) chọn module khởi chạy.
- `com.example.launch/demo.LaunchDemo` ghép **tên module** và **tên lớp main** bằng dấu `/`. Đây không phải đường dẫn tệp.
- `module` cuối câu lệnh được đưa vào `args[0]`.

Trong ví dụ này, **module name** là `com.example.launch`, còn **package/class name** là `demo.LaunchDemo`. Hai tên không cần trùng nhau.

Ngoài cú pháp `-m ten.module/ten.lop.Main`, một modular JAR hoặc module có thể có main class được cấu hình trong module descriptor; khi đó có thể chạy `java -m ten.module`. Descriptor `module-info.java` viết ở trên **chưa cấu hình main class**, nên bài này **phải** chỉ rõ `/demo.LaunchDemo`.

### Module path và classpath khác nhau ở đâu?

- **Classpath** liệt kê các thư mục/JAR chứa lớp; với các class thông thường, launcher tìm main class bằng tên lớp trên classpath.
- **Module path** giúp runtime quan sát các module có tên, đọc module descriptor, phân giải dependency và áp dụng ranh giới truy cập module.
- Cùng một chương trình có thể tương tác cả classpath và module path nếu cấu hình phù hợp, nhưng không được coi đây là hai danh sách đường dẫn có hành vi hoàn toàn giống nhau.
- **Một JAR thông thường đặt trên module path** có thể được xem như automatic module theo quy tắc JPMS; hành vi khác với modular JAR có `module-info.class`. Không phải mọi JAR trên module path đều có descriptor do tác giả tự khai báo.

Một module thiếu dependency được khai báo hoặc không thể resolve có thể thất bại **trước khi tới `main`**. Bởi vậy lỗi liên quan module path/descriptor là lỗi ở giai đoạn lập đồ thị module hoặc nạp/liên kết lớp, khác với việc `main` ném exception khi đã chạy.

### Đóng gói thành modular JAR (mở rộng)

Từ exploded module đã biên dịch, có thể tạo modular JAR và chọn main class cho nó:

```bash
jar --create --file launch-module.jar --main-class demo.LaunchDemo -C mods/com.example.launch .
java --module-path launch-module.jar -m com.example.launch modular-jar
```

**Standard output của lệnh `java`:**

```text
Chế độ: modular-jar
```

JAR trên có `module-info.class` nên được nhận diện là modular JAR. Tùy chọn `--main-class` của lệnh `jar` đặt thông tin lớp chính trong metadata phù hợp; do đó lời gọi `-m com.example.launch` có thể bỏ phần `/demo.LaunchDemo`. **Đừng lẫn** biểu diễn main class trong manifest khi chạy `-jar` với metadata main class dùng khi khởi chạy **named module**: phải xem chính xác cách công cụ đóng gói thiết lập mỗi loại.

## 6. Chế độ 4 — Chạy trực tiếp tệp nguồn bằng `java File.java`

Từ **Java 11**, Java launcher hỗ trợ **source-file mode**: biên dịch tệp nguồn trong bộ nhớ rồi thực thi lớp chính mà **không cần chạy riêng `javac` để tạo class file trên đĩa**.

Với tệp `src/demo/LaunchDemo.java` đã tạo ở bước 2:

```bash
java src/demo/LaunchDemo.java source
```

**Standard output:**

```text
Chế độ: source
```

Khác với `java -cp out demo.LaunchDemo`, đối số sau `java` ở đây là **đường dẫn tệp thực sự**, có đuôi `.java`; launcher nhận ra source-file mode, sử dụng compiler trong runtime để biên dịch nguồn vào bộ nhớ rồi chạy lớp chính. Việc khai báo `package demo;` trong tệp nguồn này không khiến bạn phải thay đường dẫn tệp bằng `demo.LaunchDemo` khi dùng source-file mode.

```text
java src/demo/LaunchDemo.java source
          │
          ├─ Nhận diện tệp nguồn / chọn source-file mode
          ├─ Biên dịch tệp nguồn trong bộ nhớ
          ├─ Nạp lớp chính đã biên dịch
          └─ Gọi main(new String[]{"source"})
```

**Không cần** thấy `out/demo/LaunchDemo.class` sau lệnh này: mặc định việc biên dịch phục vụ chính lần khởi chạy, không xuất class file bằng `-d out` như `javac`. Nếu tệp source mắc lỗi cú pháp hoặc lỗi kiểu, lỗi biên dịch có thể xuất hiện **ngay trong lệnh `java File.java`**, dù bạn không gọi `javac` tường minh.

Có thể chỉ rõ phiên bản ngôn ngữ nguồn (miễn JVM/JDK hỗ trợ):

```bash
java --source 17 src/demo/LaunchDemo.java source-17
```

**Standard output:**

```text
Chế độ: source-17
```

Một số cách viết nguồn hoặc API cần classpath/module path tương ứng. Source-file mode phù hợp cho ví dụ nhỏ, script và thử nghiệm; nó **không tự động giải quyết dependency, build nhiều module, tạo JAR phân phối hay thay thế toàn bộ quy trình build**. Với Java 17, hãy xem đây chủ yếu là cách chạy **một source file làm entry point**, không giả định nó tự quét và biên dịch cả cây dự án nhiều tệp.

### Phân biệt với `java demo.LaunchDemo`

| Câu lệnh | Launcher hiểu đối số là gì? |
| --- | --- |
| `java src/demo/LaunchDemo.java` | **Đường dẫn tệp mã nguồn**, đi qua source-file mode |
| `java -cp out demo.LaunchDemo` | **Tên lớp đã biên dịch** trên classpath |
| `java -cp out src/demo/LaunchDemo.java` | Đối số vị trí launch vẫn là đường dẫn tệp `.java`, do đó có thể kích hoạt source-file mode; `-cp out` là tùy chọn runtime/compiler chứ không đổi nó thành binary class name |
| `javac src/demo/LaunchDemo.java` | Lệnh của **compiler**, không phải lệnh khởi chạy JVM để gọi `main` |

## 7. Điểm khác nhau thực sự nằm ở giai đoạn nào trong vòng đời?

Từng chế độ thay đổi **cách tìm điểm vào** và **khâu chuẩn bị trước khi gọi `main`**, nhưng những bước JVM cốt lõi vẫn tồn tại.

### 7.1. Giai đoạn launch: phân tích lệnh và chọn entry point

Launcher đọc các tùy chọn JVM/launcher được đặt **trước launch target** rồi quyết định chế độ:

```text
java [options] <main-class> [application-arguments]
java [options] -jar <jar-file> [application-arguments]
java [options] -m <module>[/<main-class>] [application-arguments]
java [options] <source-file>.java [application-arguments]
```

Các dấu ngoặc nhọn/góc trong sơ đồ là ký hiệu mô tả, **không gõ nguyên văn vào shell**. Với cú pháp thật ở bước 3–6, `class`, `jar`, `module`, `source` lần lượt trở thành `args[0]`.

Ví dụ tùy chọn JVM phải nằm trước lớp cần chạy:

```bash
java -Xmx256m -cp out demo.LaunchDemo class
```

Kết quả vẫn là `Chế độ: class`. Nếu đặt `-Xmx256m` **sau** `demo.LaunchDemo`, chương trình nhận nó như chuỗi `args[0]`, còn bộ nhớ tối đa JVM không được cấu hình bằng đối số ấy.

### 7.2. Giai đoạn tìm và chuẩn bị lớp

- **Class launch:** loader dùng classpath để định vị `demo.LaunchDemo`.
- **JAR launch:** launcher đọc `Main-Class` từ manifest của JAR và sử dụng cách tìm lớp phù hợp chế độ `-jar`.
- **Module launch:** runtime phân giải named module từ module path, xét descriptor/dependency và tìm lớp main trong module.
- **Source-file launch:** compiler biên dịch mã nguồn trong bộ nhớ, sau đó runtime có thể nạp lớp kết quả để thực thi.

Sau khi tìm được định nghĩa lớp, JVM thực hiện **loading**, **linking** (bao gồm verification/preparation và resolution khi cần), **initialization** theo quy tắc JVM. Runtime thực thi static initialization thích hợp trước khi chạy phần tương ứng của chương trình. Không phải mọi lớp phụ thuộc đều được nạp/khởi tạo ngay lúc startup; nhiều việc diễn ra lười khi chương trình sử dụng tới.

### 7.3. Giai đoạn thực thi

Khi `main` được gọi thành công, cả bốn chế độ dùng cùng ngữ nghĩa Java cho chương trình mẫu. Bytecode có thể được interpreter xử lý hoặc JIT tối ưu/biên dịch thành mã máy; cách phân phối lớp qua thư mục, JAR, module hay source file **không tự quyết định chương trình luôn chạy bằng interpreter hay JIT**.

Trong ví dụ này, bốn kiểu khởi chạy chỉ khác **giá trị tham số truyền vào** nên có các dòng stdout khác nhau. Nếu truyền cùng một tham số, logic `LaunchDemo.main` cho cùng kết quả.

### 7.4. Giai đoạn kết thúc

`main` kết thúc không bảo đảm JVM kết thúc ngay nếu vẫn còn non-daemon threads. Khi toàn bộ điều kiện kết thúc tiến trình thỏa mãn hoặc `System.exit(...)` được gọi, runtime thực hiện quy trình shutdown thích hợp. Điều này đúng cho cả bốn kiểu launch; không có quy tắc “JAR tắt JVM khác class” chỉ vì định dạng đóng gói.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Chế độ hay liên quan | Kiểm tra |
| --- | --- | --- |
| `Could not find or load main class` | Class | `-cp` có chỉ **thư mục gốc package**? Tên có đúng `demo.LaunchDemo`? Class đã biên dịch chưa? |
| `no main manifest attribute` | `-jar` | JAR có khai báo `Main-Class` chưa? Đã dùng `jar --main-class` hoặc quy trình tạo manifest thích hợp chưa? |
| `ClassNotFoundException` / `NoClassDefFoundError` | Class/JAR và các biến thể | Dependency có tại runtime không? Classpath có phù hợp và đầy đủ không? Có lỗi khởi tạo lớp trước đó không? |
| Không tìm thấy module hoặc module không resolve | `-m` | Đúng tên module? `--module-path` trỏ đúng `mods`/modular JAR? Dependency trong `requires` có đủ? |
| Không tìm thấy main class bên trong module | `-m` | Đã ghi `-m com.example.launch/demo.LaunchDemo` hay đặt main-class metadata? |
| Lỗi `javac` ngay khi chạy `java File.java` | Source-file mode | Sửa cú pháp/kiểu mã nguồn và dependency; vì launcher đang biên dịch trong bộ nhớ |
| `UnsupportedClassVersionError` | Chạy class/JAR/module | Class file được biên dịch cho Java mới hơn runtime? Kiểm tra `java --version` và `javap -verbose` |
| Lựa chọn bộ nhớ `-Xmx` không có tác dụng | Mọi chế độ | Tùy chọn JVM có bị đặt **sau launch target** và trở thành tham số ứng dụng? |

### Bộ lệnh kiểm tra nhỏ

```bash
javap -classpath out demo.LaunchDemo
jar --list --file app.jar
java --describe-module java.base
java --version
```

- `javap` xác nhận lớp đã biên dịch và signature `main`.
- `jar --list` xem các entry của JAR; có thể kiểm tra manifest khi gặp vấn đề về `Main-Class`.
- `java --describe-module java.base` cho thấy Java runtime hiểu khái niệm named module và cung cấp module nền tảng; với ứng dụng cụ thể, mô tả module mục tiêu theo cấu hình module path phù hợp.
- `java --version` kiểm tra runtime đang dùng khi gặp lỗi tương thích bytecode.

## 9. Chọn cách khởi chạy phù hợp

| Nhu cầu | Cách thường hợp lý | Lý do |
| --- | --- | --- |
| Học nhanh luồng `.java → .class → JVM`, quan sát `javap` | `javac`, rồi `java -cp ... main.Class` | Nhìn rõ sản phẩm biên dịch và việc tìm class theo package |
| Chuyển một chương trình có entry point cho người khác chạy | `java -jar app.jar` | Một đường dẫn JAR và entry point ở manifest; vẫn phải đóng gói/cấp dependency đúng |
| Dự án thực sự thiết kế theo JPMS, muốn khai báo dependency/encapsulation module | `java --module-path ... -m ...` | Runtime phân giải module và áp dụng ranh giới module |
| Thử một source file ngắn trên JDK phù hợp | `java File.java` | Không cần lệnh `javac` riêng, ít bước thao tác |
| Muốn kiểm tra tác động của việc đóng gói | Chạy **cùng lớp** bằng `-cp`, `-jar`, `-m` | Giúp tách lỗi launch/dependency khỏi lỗi của `main` |

Tránh quyết định chỉ dựa trên tên file: **một JAR có thể được dùng như mục classpath hoặc executable JAR; một modular JAR cũng có thể được launch qua module path**. Lệnh `java` mới cho biết launcher đang chọn cơ chế nào.

## 10. Bài thực hành kiểm chứng bốn đường vào

Sử dụng đúng một mã nguồn `LaunchDemo.java` ở mục 2 và thực hiện:

1. **Class mode:** biên dịch vào `out/`; chạy `java -cp out demo.LaunchDemo class`; đọc `Chế độ: class`.
2. **JAR mode:** tạo `app.jar` từ `out/`; chạy `java -jar app.jar jar`; đọc `Chế độ: jar`.
3. **Module mode:** thêm `module-info.java`, biên dịch vào `mods/com.example.launch/`; chạy `java --module-path mods -m com.example.launch/demo.LaunchDemo module`; đọc `Chế độ: module`.
4. **Source-file mode:** chạy trực tiếp `java src/demo/LaunchDemo.java source`; đọc `Chế độ: source`.

Thử có kiểm soát:

- Bỏ `-cp out` ở lời gọi tên lớp và quan sát khả năng tìm lớp thay đổi ra sao. Kết quả còn phụ thuộc current directory và biến môi trường classpath; vì vậy hãy xem cấu hình thực tế.
- Đổi lệnh `java -jar app.jar jar` thành `java -cp app.jar demo.LaunchDemo classpath-jar`; chương trình chạy với cùng bytecode nhưng launcher nhận **tên lớp** thay vì đọc `Main-Class`.
- Ở module mode, thay tên `com.example.launch` thành tên không tồn tại; lỗi xảy ra khi resolve/chọn module, **trước** khi logic `main` bắt đầu.
- Đưa một lỗi kiểu vào source (chẳng hạn `int n = "sai";` trong `main`) và chạy source-file mode: lần này lệnh `java` báo vấn đề biên dịch vì compiler được gọi ngầm. Sau khi sửa, chạy lại để khôi phục chương trình hợp lệ.

### Tự kiểm tra

**1.** `java -jar app.jar` sẽ khởi chạy lớp `demo.LaunchDemo` dù manifest không có `Main-Class`? **Không**; chế độ `-jar` cần entry point thích hợp trong manifest.

**2.** Vì sao `java -cp out demo.LaunchDemo` dùng dấu chấm nhưng `java src/demo/LaunchDemo.java` dùng dấu gạch chéo? Câu đầu dùng **tên lớp trong package**, câu sau dùng **đường dẫn tệp mã nguồn**.

**3.** `java File.java` bỏ qua hoàn toàn biên dịch? **Không**; source-file mode vẫn biên dịch mã nguồn, chỉ là **không yêu cầu người dùng chạy `javac` riêng và không cần xuất class file ra đĩa**.

**4.** Có phải chỉ ứng dụng module mới chạy trên JVM hỗ trợ JIT? **Không**; JIT là cơ chế thực thi bytecode của JVM, độc lập lựa chọn class/JAR/module/source-file launch.

**5.** Khi nào tham số `-Xmx256m` trở thành tham số ứng dụng? Khi đặt **sau** tên main class/JAR/module/source-file launch target; launcher đã chuyển phần đối số tiếp theo vào `main(String[] args)`.

Điểm then chốt để ghi nhớ: **class mode** chọn main class từ classpath; **JAR mode** chọn qua manifest; **module mode** chọn bằng tên module và main class hoặc metadata module; **source-file mode** biên dịch mã nguồn trong bộ nhớ rồi chạy. Chỉ cần nhìn chính xác target và các đường dẫn của lệnh `java`, bạn sẽ khoanh vùng phần lớn lỗi “không khởi động được” trước khi đi sâu vào code của ứng dụng.