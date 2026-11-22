# Chế độ `java -jar` và các quy tắc classpath liên quan

`java -jar` là một chế độ khởi chạy ứng dụng Java từ **executable JAR**. Điểm cần hiểu không phải chỉ là cách gọi lệnh, mà là **JVM xác định lớp `main` và đường dẫn tìm những lớp/phụ thuộc khác như thế nào**. Khi chọn chế độ này, các tùy chọn classpath thông thường bị bỏ qua; thay vào đó, JAR được chỉ định cùng thuộc tính `Class-Path` trong manifest (nếu có) quyết định các mục ứng dụng trên đường tìm kiếm lớp.

Một mô hình ngắn:

```text
java [tùy chọn JVM] -jar app.jar [tham số chương trình]
                             |
                             v
                  Đọc META-INF/MANIFEST.MF
                             |
                    Main-Class: demo.Main
                             |
                    Class-Path: lib/helper.jar
                             |
                 +-----------+-------------+
                 |                         |
             app.jar               lib/helper.jar
                 |                         |
          demo/Main.class        helper/Message.class
                 |                         |
                 +----- ClassLoader -------+
                             |
                       main(String[])
```

**Kết luận trọng tâm:** `java -jar app.jar` khác `java -cp app.jar demo.Main`. Hai cách có thể chạy cùng bytecode nhưng **cơ chế chọn main class và cấu hình classpath không giống nhau**.

## 1. Các hình thức khởi chạy phải phân biệt

| Chế độ | Ví dụ | Cách chọn entry point | Classpath ứng dụng |
|---|---|---|---|
| Main class | `java -cp "out:lib/*" demo.Main` | Ghi rõ tên binary của class có `main` | Từ `-cp` / `--class-path`, hoặc `CLASSPATH` nếu không ghi option |
| Executable JAR | `java -jar app.jar` | Đọc `Main-Class` từ manifest của `app.jar` | JAR được chỉ định, cộng các mục `Class-Path` hợp lệ trong manifest |
| Named module | `java --module-path mods -m my.module/demo.Main` | Module/main class theo quy tắc JPMS | Module path và module resolution; không đồng nhất với chế độ classpath |

Với ví dụ dòng đầu, trên **Windows** dùng dấu `;` thay vì dấu `:` để phân cách các mục classpath:

```powershell
java -cp "out;lib/*" demo.Main
```

Đừng dùng dấu `;` để phân tách các mục trong manifest `Class-Path`: cú pháp manifest khác với cú pháp đối số `-cp`.

### Cú pháp `java -jar`

```bash
java [JVM options] -jar path/to/app.jar [program arguments]
```

- `java`: trình khởi chạy JVM.
- Các tùy chọn JVM, ví dụ `-Xmx512m` hay `-Dapp.env=dev`, đặt **trước `-jar`**.
- `-jar`: chuyển sang chế độ tìm entry point từ manifest.
- `path/to/app.jar`: tệp executable JAR.
- Những từ phía sau tên JAR là **đối số chương trình** mà `main(String[] args)` nhận được; chúng không còn được hiểu là tùy chọn JVM của launcher.

Ví dụ:

```bash
java -Xmx512m -Dapp.env=dev -jar app.jar alpha beta
```

Ứng dụng nhận hai argument `alpha` và `beta`, còn `app.env` là system property do JVM đặt. Nếu viết `java -jar app.jar -Xmx512m` thì `-Xmx512m` sẽ được truyền cho chương trình dưới dạng argument (trừ khi ứng dụng tự xử lý nó), **không** đặt giới hạn heap.

## 2. `Main-Class` chọn entry point cho `-jar`

Một executable JAR chuẩn chứa manifest tại `META-INF/MANIFEST.MF`, ví dụ:

~~~text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar

~~~

`Main-Class: demo.Main` dùng **binary name**; entry class thực tế trong archive là `demo/Main.class`. Trên Java 17, bài này dùng `public static void main(String[] args)`. Thiếu `Main-Class` thường báo `no main manifest attribute` nhưng không làm JAR thư viện trở thành vô giá trị.

Có thể ghi entry point bằng `jar --create --file app.jar --main-class demo.Main -C build/app .` hoặc cung cấp manifest rõ ràng qua `--manifest MANIFEST.MF`. Hai cách đều **không tự nhúng dependency**. Định dạng manifest và quy tắc đóng gói chi tiết được dạy ở bài **JAR, manifest Main-Class và Class-Path**; phần này tập trung vào việc launcher chọn chế độ chạy.

## 3. Điều gì xảy ra với `-cp` và `CLASSPATH` khi có `-jar`?

Với `java -jar app.jar`, launcher sử dụng JAR được chỉ định làm nguồn class ứng dụng, cùng các entry hợp lệ từ `Class-Path` trong manifest. Những cấu hình **classpath thông thường** khác không được dùng để mở rộng user classpath của chế độ này.

| Cấu hình | `java -cp ... demo.Main` | `java -jar app.jar` |
|---|---|---|
| `-cp` / `-classpath` / `--class-path` | Được dùng làm classpath | **Bị bỏ qua** trong chế độ `-jar` |
| Biến môi trường `CLASSPATH` | Được dùng nếu không có classpath option thay thế | **Bị bỏ qua** đối với tìm user classes trong chế độ `-jar` |
| `Main-Class` của `app.jar` | Không cần nếu đã ghi class trên CLI | **Cần** để xác định main class |
| Manifest `Class-Path` | Có thể được áp dụng cho những JAR trên classpath phù hợp | **Có thể được áp dụng** để tìm dependency của executable JAR |
| Các option JVM như `-D...`, `-Xmx...` | Hoạt động khi đặt đúng vị trí | **Vẫn hoạt động** khi đặt trước `-jar` |

Ví dụ dễ mắc lỗi:

```bash
java -cp "lib/*" -jar app.jar
```

Không được suy luận rằng `lib/*` sẽ được dùng để thêm mọi JAR trong thư mục `lib`. Khi chọn `-jar`, `-cp "lib/*"` không có hiệu lực như bạn kỳ vọng.

Tương tự, chỉ đặt `CLASSPATH=lib/helper.jar` ngoài môi trường rồi chạy `java -jar app.jar` **không thay thế** việc khai báo dependency đúng cách.

**Phân biệt:** quy tắc trên nói về classpath ứng dụng khi khởi chạy `-jar`, **không có nghĩa tất cả tùy chọn JVM khác đều bị tắt**. Những cơ chế như bootstrap/platform classes, native library path, module system, java agents hoặc framework launcher có quy tắc riêng.

### Còn wildcard `*` thì sao?

Với classpath CLI bình thường:

```bash
java -cp "app.jar:lib/*" demo.Main
```

Launcher hỗ trợ wildcard cho **tệp `.jar` trong thư mục** theo cú pháp classpath. Dấu phân cách ví dụ trên là `:` ở Linux/macOS; trên Windows là `;`. Wildcard classpath không đệ quy, và thứ tự JAR được mở rộng không nên được dùng để bảo đảm thứ tự phụ thuộc.

Nhưng manifest `Class-Path` có cú pháp **relative URL entries được ngăn cách bằng dấu cách**; không có phép mở rộng wildcard kiểu `-cp "lib/*"`. Vì vậy:

```text
Class-Path: lib/*
```

**Không** tương đương “nạp tất cả JAR trong thư mục lib”. Cần liệt kê các file hợp lệ, ví dụ:

```text
Class-Path: lib/helper.jar lib/json.jar lib/logging.jar
```

Các thư viện được ghi cách nhau bằng khoảng trắng, **không** bằng dấu `:`, `;` hoặc dấu phẩy. Việc mỗi mục có tìm thấy được hay không còn phụ thuộc quy tắc đường dẫn ở phần tiếp theo.

## 4. `Class-Path` trong manifest khi chạy `-jar`

Giả sử `release/app.jar` nằm cạnh `release/lib/helper.jar`. Manifest `app.jar` khai báo `Class-Path: lib/helper.jar` thì dependency được resolve **tương đối với vị trí của `app.jar`**, kể cả khi khởi chạy từ thư mục khác.

Không nhầm dấu phân cách của hai chế độ: với `java -cp`, Windows dùng `;` còn Unix dùng `:`; manifest `Class-Path` dùng **danh sách relative URL cách nhau bằng khoảng trắng**. Nó **không mở rộng wildcard**: `Class-Path: lib/*` không có nghĩa mọi JAR trong thư mục. Entry kết thúc bằng `/` dùng cho directory, entry không kết thúc như vậy dùng cho JAR; path không hợp lệ/không tồn tại có thể bị bỏ qua. Manifest cần một main-section `Class-Path` hợp lệ; với dòng vật lý quá dài, công cụ `jar` xử lý quy tắc gập dòng theo byte UTF-8.

Phân phối executable JAR vì thế phải mang đúng cây thư mục library bên cạnh JAR, hoặc dùng launcher/đóng gói khác. Bài trước giải thích chi tiết chuẩn URL/manifest; ví dụ sau đây kiểm chứng trực tiếp việc `-jar` bỏ qua `-cp` với một class `side.Extra` nằm ở ngoài.

## 5. Ví dụ đầy đủ Java 17+: `-jar` tìm dependency qua manifest nhưng bỏ qua `-cp`

Ví dụ tạo hai JAR:

- `app.jar`: chứa class entry point `demo.Main`.
- `lib/helper.jar`: chứa class thư viện `helper.Message`.

Ta còn biên dịch riêng `side.Extra` vào thư mục `extra/` để chứng minh rằng classpath `-cp extra` bị bỏ qua khi dùng `-jar`. Nếu chạy ở classpath mode thông thường, class `side.Extra` sẽ được tìm thấy.

### 5.1. Cấu trúc nguồn

```text
project/
  src/
    helper/
      Message.java
    demo/
      Main.java
    side/
      Extra.java
  MANIFEST.MF
  build/                 (tạo khi biên dịch)
  extra/                 (tạo khi biên dịch)
  lib/
    helper.jar           (tạo khi đóng gói)
  app.jar                (tạo khi đóng gói)
```

### 5.2. `src/helper/Message.java`

```java
package helper;

public final class Message {
    private Message() { }

    public static String text() {
        return "Hello from helper";
    }
}
```

### 5.3. `src/side/Extra.java`

```java
package side;

public final class Extra {
    private Extra() { }
}
```

`Extra` không được đưa vào `app.jar` và cũng không nằm trong manifest `Class-Path`. Nó tồn tại riêng trong `extra/` sau biên dịch.

### 5.4. `src/demo/Main.java`

```java
package demo;

import helper.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println("message: " + Message.text());
        System.out.println("args: " + args.length);
        System.out.println("mode: "
                + System.getProperty("mode", "unset"));

        try {
            Class.forName("side.Extra");
            System.out.println("extra: visible");
        } catch (ClassNotFoundException ex) {
            System.out.println("extra: absent");
        }
    }
}
```

Ý nghĩa:

- `Main` cần `helper.Message` để biên dịch và để thực thi.
- `Class.forName("side.Extra")` tìm lớp bằng tên; nếu không nhìn thấy ở loader của caller, nó ném `ClassNotFoundException`.
- Dùng `Class.forName` trong `try/catch` để chương trình **vẫn chạy được** ngay cả khi Extra không có trên classpath.
- `args.length` cho phép thấy tham số sau `app.jar` được chuyển đến chương trình.
- Property `mode` cho phép thấy tùy chọn `-Dmode=...` phải đứng trước `-jar`.

### 5.5. `MANIFEST.MF`

Tạo file text **`MANIFEST.MF`** ở thư mục `project`:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: lib/helper.jar

```

**Bắt buộc có dòng kết thúc (và tốt nhất là dòng trống cuối)** cho main section. `Main-Class` dùng tên `demo.Main`, còn `Class-Path` trỏ tới `lib/helper.jar` tính từ vị trí của `app.jar`.

### 5.6. Biên dịch và đóng gói

Các lệnh sau dùng **Bash trên Linux/macOS** (hoặc môi trường Bash tương ứng trên Windows) và được chạy từ thư mục `project`:

```bash
mkdir -p build/helper build/app lib extra

javac -d build/helper src/helper/Message.java
jar --create --file lib/helper.jar -C build/helper .

javac -cp lib/helper.jar -d build/app src/demo/Main.java
jar --create --file app.jar --manifest MANIFEST.MF -C build/app .

javac -d extra src/side/Extra.java
```

Giải thích thứ tự:

1. Biên dịch thư viện `Message` trước.
2. Tạo `lib/helper.jar` từ các `.class` của thư viện.
3. Biên dịch `Main` với `-cp lib/helper.jar` để **javac** nhìn thấy `helper.Message`.
4. Tạo executable `app.jar` chứa `demo.Main` và manifest. **Đây là bước đóng gói**, không tự chép `helper.jar` vào `app.jar`.
5. Biên dịch `Extra` vào thư mục riêng để thử hai chế độ.

**Lưu ý:** `javac -cp ...` là **classpath tại thời điểm biên dịch**. Nó không tự động cấu hình classpath cho lần chạy `java -jar` sau này. Đó là lý do manifest cần `Class-Path`.

### 5.7. Chạy đúng chế độ `-jar`

```bash
java -jar app.jar
```

**Stdout chính xác:**

```text
message: Hello from helper
args: 0
mode: unset
extra: absent
```

Lệnh chạy tìm được `helper.Message` dù `app.jar` không chứa thư viện, vì manifest chỉ tới `lib/helper.jar`. Ngược lại, `side.Extra` nằm riêng ở `extra/` không có trong đường tìm kiếm.

Thử thêm `-cp extra` trước `-jar`:

```bash
java -cp extra -jar app.jar
```

**Stdout vẫn giống hệt:**

```text
message: Hello from helper
args: 0
mode: unset
extra: absent
```

`-cp extra` **không** làm class `side.Extra` xuất hiện: chế độ `-jar` bỏ qua classpath option. Đây là khác biệt mà ví dụ muốn chứng minh.

### 5.8. Chạy ở classpath mode thay vì `-jar`

Trên Linux/macOS:

```bash
java -cp "app.jar:lib/helper.jar:extra" demo.Main
```

Trên Windows PowerShell/cmd, dùng dấu `;`:

```powershell
java -cp "app.jar;lib/helper.jar;extra" demo.Main
```

**Stdout trong trường hợp này:**

```text
message: Hello from helper
args: 0
mode: unset
extra: visible
```

Ở đây launcher dùng classpath do chúng ta chỉ định và lấy `demo.Main` từ đối số CLI, nên `side.Extra` cũng tìm được. Kết quả chứng minh **chế độ khởi chạy**, không phải tên đuôi `.jar`, quyết định cách cấu hình classpath.

### 5.9. Tùy chọn JVM và arguments ở đâu?

```bash
java -Dmode=prod -jar app.jar alpha beta
```

**Stdout:**

```text
message: Hello from helper
args: 2
mode: prod
extra: absent
```

Vì `-Dmode=prod` đứng trước `-jar`, JVM nhận property này. `alpha beta` đứng sau JAR nên `args.length == 2`. Nếu chuyển `-Dmode=prod` ra sau `app.jar` thì ứng dụng sẽ nhận nó như một argument và property `mode` giữ giá trị mặc định `unset` (giả sử chưa có nguồn cấu hình khác).

## 6. Khi thư viện nằm ở vị trí khác JAR

Giả sử:

```text
dist/
  app.jar
  lib/helper.jar
```

Chỉ cần manifest trong `app.jar` khai báo `Class-Path: lib/helper.jar`. Lệnh:

```bash
java -jar dist/app.jar
```

sẽ giải quyết dependency theo vị trí của **`dist/app.jar`**, nghĩa là `dist/lib/helper.jar`, dù người dùng thực thi lệnh từ thư mục cha.

Nếu di chuyển `app.jar` vào thư mục khác nhưng không chuyển thư mục `lib` tương ứng, manifest trở thành tham chiếu sai. Đây là nguyên nhân phổ biến dẫn đến lỗi “chạy được trên máy build, lỗi trên máy triển khai”.

### Manifest `Class-Path` có cho phép JAR lồng bên trong JAR không?

Không theo cách mặc định của Java launcher. Nếu bạn đóng gói `lib/helper.jar` **như một entry nằm bên trong `app.jar`**, JVM class loader mặc định không tự coi entry JAR lồng đó như một mục classpath độc lập.

Các hướng đóng gói phổ biến:

1. **Thin JAR + thư viện ngoài:** dùng `Main-Class` và manifest `Class-Path` tới các JAR ở thư mục kề bên.
2. **Uber/Fat JAR:** công cụ build thường gộp các `.class` và tài nguyên phụ thuộc vào một JAR có cấu trúc phù hợp, đồng thời xử lý xung đột service resources khi cần.
3. **Executable archive với launcher riêng:** framework (chẳng hạn launcher chuyên dụng cho nested JARs) tự cung cấp cách tìm dependency; cần đọc quy tắc của framework thay vì áp dụng mặc định `java -jar` cho cấu trúc nested.

**Đừng giả định** mọi “fat jar” có cấu trúc giống nhau. Một JAR có thể chạy bằng `java -jar` nhờ một `Main-Class` của launcher framework chứ không phải class chứa `main` ứng dụng mà bạn viết.

## 7. Classpath, class loader và tính nhìn thấy của lớp

Với ứng dụng Java dùng classpath thông thường, các mục executable JAR và manifest dependency được dùng để cấu hình **đường tìm kiếm** cho bộ nạp lớp ứng dụng (system/application class loader trong cấu hình phổ biến).

```text
ClassLoader
    |
    | loadClass("helper.Message")
    v
Ứng dụng tìm class theo loader hierarchy và classpath
    |
    +-- app.jar               (không có helper/Message.class)
    |
    +-- lib/helper.jar        (có helper/Message.class)
    |
    v
Runtime Class<helper.Message>
```

Việc khai báo đường tìm kiếm không có nghĩa mọi class đều được load ngay. Khi mã chạy `Message.text()`, runtime cần lớp `helper.Message` thích hợp. Nếu file thư viện không tìm được, có thể phát sinh lỗi tại thời điểm JVM cần resolve/load kiểu, không nhất thiết ngay khi `java` bắt đầu.

**Một điểm khác:** `java -jar` không tự nạp lại hoặc override các lớp Java nền tảng do bootstrap/platform loader cung cấp. Class loader hierarchy, định danh kiểu `(binary name, defining loader)` và các giới hạn của JPMS vẫn áp dụng.

### Vì sao không nên lẫn `-jar` và `-cp` khi điều tra lỗi?

Hai lệnh:

```bash
java -jar app.jar
java -cp "app.jar:lib/helper.jar" demo.Main
```

có thể cho cùng output ở ví dụ đơn giản, **nhưng không chứng minh hai chế độ đồng nhất**. Chế độ đầu dựa vào `Main-Class` và manifest `Class-Path`; chế độ thứ hai lấy tên class và classpath trực tiếp từ CLI.

Nếu `Class-Path` trong manifest sai, lệnh thứ hai có thể chạy thành công vì `-cp` được chỉ định rõ, còn lệnh thứ nhất thất bại. Đây là phép đối chiếu rất hữu ích khi debug packaging.

## 8. Liên hệ với module path (JPMS)

Java 9+ có hệ thống module, nhưng cần phân biệt rõ:

- `java -jar app.jar` là **khởi chạy JAR theo manifest**, và lớp ứng dụng thông thường nằm trong **unnamed module** của loader liên quan.
- `java --module-path mods -m module.name/main.Class` là **khởi chạy module**, dựa vào module descriptor/JPMS.
- Một JAR có thể được đặt trên classpath trong một chế độ, nhưng khi chạy dưới module path ở ngữ cảnh khác có thể trở thành named/automatic module theo các quy tắc tương ứng.
- Cờ `--module-path` không phải một cách thay thế trực tiếp cho `Class-Path` trong manifest, và việc một dependency có cần JPMS resolution còn phụ thuộc kiểu chương trình.

Đối với phần lớn ứng dụng học Java Core bằng `-jar` + thư viện thông thường, trước tiên hãy debug **classpath của executable JAR**; chỉ chuyển sang phân tích module khi dự án thực sự sử dụng named modules.

## 9. Những lỗi thường gặp và cách xác định nguyên nhân

### 9.1. `no main manifest attribute, in app.jar`

**Nguyên nhân:** thiếu `Main-Class` trong main section của manifest.

**Kiểm tra:**

```bash
jar --describe-module --file app.jar
unzip -p app.jar META-INF/MANIFEST.MF
```

Lệnh `unzip -p` là tiện ích hệ điều hành tùy chọn; nếu không có, dùng `jar --extract --file app.jar META-INF/MANIFEST.MF` ở thư mục kiểm tra riêng rồi mở tệp manifest. Lệnh `jar --describe-module` chỉ hữu ích cho thông tin module, **không thay thế việc đọc manifest** để xác minh `Main-Class`.

**Khắc phục:** tạo JAR với `--main-class` hoặc một manifest có `Main-Class: demo.Main` đúng tên, sau đó đóng gói lại.

### 9.2. `Could not find or load main class demo.Main`

**Nguyên nhân có thể:** manifest chỉ sai binary name, package/directory layout trong JAR không đúng, class không được đóng gói, class không nạp được do thiếu dependency, hoặc tên lớp trong cấu hình chạy nhầm.

**Kiểm tra:**

```bash
jar --list --file app.jar
```

Bên trong JAR phải có entry class đúng tên tương ứng, ví dụ `demo/Main.class`. Đừng nhầm `Main-Class: demo.Main` với `Main-Class: demo/Main`.

### 9.3. `NoClassDefFoundError` hoặc `ClassNotFoundException` cho dependency

**Nguyên nhân thường thấy:** `helper.Message` không có trong `app.jar` và `Class-Path` không trỏ đúng tới `lib/helper.jar`, hoặc dependency của helper còn thiếu.

**Kiểm tra theo thứ tự:**

1. Xác định tên nhị phân của class không nạp được.
2. Tìm class đó trong JAR phụ thuộc thích hợp.
3. Kiểm tra `Class-Path` trong manifest của JAR thực sự đang chạy.
4. Resolve đường dẫn **tương đối với JAR**; xác nhận file tồn tại ở máy chạy.
5. Kiểm tra tên file, chữ hoa/thường, ký tự URL, quyền đọc và manifest không bị lỗi xuống dòng.
6. So sánh `java -jar app.jar` với classpath mode chỉ định rõ cả JAR.
7. Xem nguyên nhân gốc và stack trace; `NoClassDefFoundError` còn có thể xuất hiện sau một lần class initialization thất bại, không chỉ khi thiếu JAR.

### 9.4. `java -cp lib/* -jar app.jar` vẫn không tìm được class

**Giải thích:** các classpath option thông thường không có hiệu lực trong chế độ `-jar`. Đặt dependency trong manifest `Class-Path`, đóng gói phù hợp, hoặc chuyển hẳn sang chế độ `java -cp ... demo.Main`.

### 9.5. Đặt `Class-Path: lib/*` nhưng không tìm được thư viện

**Giải thích:** wildcard của `-cp` không chuyển sang manifest `Class-Path`. Ghi từng JAR theo relative URL hợp lệ, hoặc dùng công cụ build sinh manifest.

### 9.6. Chạy từ thư mục khác bị lỗi

**Điều tra:** nếu thư viện được tham chiếu từ manifest, URL được giải quyết theo vị trí JAR; nếu ứng dụng mở file cấu hình bằng đường dẫn tương đối trong code Java (ví dụ `Path.of("config/app.properties")`), đường dẫn code có thể lại tương đối với **working directory**. Hai phép resolve khác nhau.

**Khắc phục:** phân biệt dependency URL trong manifest với file system path do ứng dụng tự sử dụng. Đừng sửa `Class-Path` khi lỗi thực chất ở mã mở tệp cấu hình.

### 9.7. Chạy từ IDE thành công, phát hành JAR thất bại

IDE thường cấu hình toàn bộ dependency thành classpath riêng. Khi tạo executable JAR, manifest có thể thiếu `Class-Path` hoặc artifact đóng gói thiếu nội dung.

**Khắc phục:** kiểm tra lệnh JVM mà IDE dùng, manifest artifact cuối cùng và cấu trúc thư mục triển khai; thử chạy bằng chính `java -jar` trong môi trường clean.

## 10. Checklist đóng gói executable JAR

Trước khi phát hành:

- [ ] Có file JAR thật sự tồn tại và đọc được.
- [ ] Manifest có `Main-Class` hợp lệ trong main section.
- [ ] Tên package và đường dẫn `.class` trong JAR khớp với `Main-Class`.
- [ ] Tất cả dependency runtime tồn tại ở vị trí mà manifest `Class-Path` hợp lệ trỏ tới, hoặc đã được đóng gói đúng kiểu fat/launcher.
- [ ] Không dựa vào `CLASSPATH`, `-cp` hay đường dẫn chỉ có trong IDE để chạy `java -jar`.
- [ ] Nếu dùng manifest `Class-Path`, các entry được ngăn bằng dấu cách, không dùng wildcard, và relative path được resolve theo vị trí JAR.
- [ ] Tùy chọn JVM được đặt trước `-jar`; argument chương trình đặt phía sau JAR.
- [ ] Kiểm tra chương trình từ một thư mục làm việc khác để phát hiện nhầm lẫn working-directory.
- [ ] Kiểm tra module/launcher riêng nếu dự án dùng JPMS hoặc executable archive không theo cấu trúc classpath JAR thông thường.
- [ ] Dùng Java runtime tương thích với version của `.class` và thư viện, rồi chạy thử artifact sau khi đóng gói.

## 11. Tự kiểm tra

**Câu 1.** Manifest có `Main-Class: demo.Main` nhưng không có `Class-Path`. `demo.Main` dùng một thư viện JAR nằm ở `lib/helper.jar`. Lệnh `java -cp lib/helper.jar -jar app.jar` có phải cách chuẩn để đưa helper vào đường tìm kiếm không?

**Đáp án:** Không. `-cp` bị bỏ qua trong `-jar`. Cần cấu hình manifest `Class-Path: lib/helper.jar`, đóng gói dependency theo một cách khác phù hợp, hoặc chuyển sang `java -cp ... demo.Main`.

**Câu 2.** Manifest của `release/app.jar` ghi `Class-Path: lib/helper.jar`. Chạy lệnh từ thư mục cha. Đường dẫn nào được dùng?

**Đáp án:** `release/lib/helper.jar`, vì manifest `Class-Path` resolve theo vị trí của JAR chứa manifest.

**Câu 3.** Viết `Class-Path: lib/*` có giống `java -cp "lib/*"` không?

**Đáp án:** Không. Wildcard expansion là quy tắc của classpath CLI; manifest cần relative URL entries hợp lệ, thường là từng file JAR.

**Câu 4.** Hai lệnh `java -jar app.jar` và `java -cp app.jar demo.Main` có luôn tương đương không?

**Đáp án:** Không. Lệnh đầu lấy entry point từ manifest và dùng các phụ thuộc manifest; lệnh sau lấy class name và classpath từ CLI. Chúng chỉ có thể tình cờ cho cùng hành vi trong cấu hình đơn giản.

**Câu 5.** `java -Dmode=prod -jar app.jar hi` và `java -jar app.jar -Dmode=prod` có đặt cùng JVM property không?

**Đáp án:** Không. Ở lệnh đầu `-Dmode=prod` là option JVM; ở lệnh sau nó là argument của `main`.

**Câu 6.** Một JAR chứa file `lib/helper.jar` **bên trong archive**. Manifest ghi `Class-Path: lib/helper.jar`. JVM mặc định có tự truy cập nested archive đó như một dependency không?

**Đáp án:** Không. Mục manifest là relative URL tham chiếu bên ngoài JAR theo ngữ cảnh JAR; nested JAR cần launcher/cơ chế đóng gói đặc biệt hoặc gộp class/tài nguyên đúng cách.

## 12. Sơ đồ quyết định khi ứng dụng không tìm thấy class

```text
Chương trình chạy theo cách nào?
             |
       +-----+------+
       |            |
    java -jar      java -cp / --class-path
       |            |
Đọc manifest       Kiểm tra classpath CLI
       |            |  
Main-Class đúng?   Các mục theo dấu phân cách OS?
       |
Class-Path có relative URL hợp lệ?
       |
Resolve theo thư mục của JAR
       |
Dependency có tồn tại trong thư mục/JAR được chỉ?
       |
JVM/loader có quyền truy cập và bytecode phù hợp?
       |
Nếu vẫn lỗi: kiểm tra type name, module, phụ thuộc bắc cầu,
class initialization, classloader và lỗi gốc.
```

**Tóm tắt:** `java -jar` tìm `main` qua `Main-Class` và thiết lập đường tìm kiếm ứng dụng từ executable JAR cùng `Class-Path` trong manifest. `-cp`/`CLASSPATH` thường dùng với classpath mode nhưng **không mở rộng classpath của `-jar`**. Manifest `Class-Path` dùng **relative URLs**, phân cách **bằng dấu cách** và resolve **tương đối vị trí JAR**, chứ không phải wildcard/path separator của shell.

### Nguồn tham khảo chính thức

- [Java SE 17 — The java Command: các chế độ chạy và `-jar`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Java SE 17 — JAR File Specification: manifest và `Class-Path`](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Java SE 17 — ClassLoader API: system loader và JAR manifest classpath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
