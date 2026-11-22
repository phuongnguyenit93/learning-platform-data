# Khai báo classpath cho dependency cần thiết khi chạy chương trình một tệp (Java 11+)

## 1. Vì sao chương trình một tệp vẫn cần classpath?

Từ **Java 11**, có thể chạy trực tiếp một tệp nguồn `.java` bằng trình khởi chạy `java`:

```bash
java App.java
```

Java tự biên dịch mã nguồn cần thiết rồi chạy chương trình; với ví dụ đơn giản, không cần thực hiện riêng `javac App.java` và `java App`. Cơ chế này thường gọi là **source-file mode** (JEP 330).

Tuy nhiên, một tệp `App.java` vẫn có thể gọi đến **dependency** bên ngoài JDK, chẳng hạn một thư viện xử lý JSON hoặc một lớp trợ giúp đã đóng gói thành JAR. Khi đó Java cần biết nơi tìm các lớp đã được biên dịch của dependency. **Classpath** là danh sách thư mục, tệp `.jar` hoặc `.zip` mà Java dùng để tìm lớp; nó không tự tải thư viện từ Internet.

Ví dụ, nếu `App.java` viết `import demo.util.Greeting;` và `Greeting` chỉ nằm trong `lib/greeting.jar`, chạy `java App.java` sẽ thiếu dependency. Cách khai báo trực tiếp là:

```bash
java --class-path lib/greeting.jar App.java
```

Có thể thay `--class-path` bằng `-cp` hoặc `-classpath`. Trong source-file mode, tùy chọn classpath được dùng **khi biên dịch nguồn và khi chạy chương trình**. Đặt nó **trước tên tệp nguồn**.

Bài này tập trung vào cách khai báo dependency đã được biên dịch trong JAR hoặc thư mục `.class`; đây vẫn là kỹ thuật có hiệu lực trên các bản Java hiện đại.

## 2. Cú pháp cơ bản

```text
java [tùy chọn JVM] --class-path <đường-dẫn-classpath> App.java [tham số chương trình]
java -cp <đường-dẫn-classpath> App.java [tham số chương trình]
```

Ví dụ:

```bash
# Một JAR cụ thể
java -cp lib/greeting.jar App.java

# Tất cả JAR trực tiếp trong thư mục lib
java -cp "lib/*" App.java

# Tệp nguồn nhận tham số tên từ command line
java -cp lib/greeting.jar App.java Alice
```

Phân biệt các thành phần:

- **`java`**: trình khởi chạy chương trình trên JDK/JRE thích hợp.
- **`-cp` / `--class-path`**: thiết lập nơi tìm các lớp dependency.
- **`lib/greeting.jar`**: một tệp JAR có sẵn; Java không tự tạo hoặc tải JAR khi nhận đường dẫn này.
- **`App.java`**: tệp nguồn chương trình chính, làm cho launcher dùng source-file mode.
- **`Alice`**: tham số truyền cho `main(String[] args)`, không phải một phần classpath.

Lưu ý: `java App.java -cp lib/greeting.jar` **sai mục đích**; ở vị trí sau `App.java`, chuỗi `-cp` và đường dẫn đi vào `args` thay vì cấu hình classpath.

## 3. Ví dụ chạy trọn vẹn: tự tạo dependency JAR rồi gọi từ một tệp nguồn

Ví dụ dùng một lớp nhỏ `Greeting` để mô phỏng thư viện bên ngoài. Trong ứng dụng thực, bạn thường **đã có sẵn** tệp JAR từ thư viện cần sử dụng; bước tạo JAR dưới đây chỉ để bài tập tự chạy được mà không phải tải dependency từ mạng.

Tạo thư mục bài thực hành với hai tệp nguồn:

```text
demo/
├── App.java
├── src/
│   └── demo/
│       └── util/
│           └── Greeting.java
├── classes/             # Thư mục biên dịch, tạo ở bước tiếp theo
└── lib/                 # Chứa JAR dependency
```

**Tệp `src/demo/util/Greeting.java`** — mã nguồn thư viện phụ trợ:

```java
package demo.util;

public class Greeting {
    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

**Tệp `App.java`** — chương trình một tệp cần chạy trực tiếp:

```java
import demo.util.Greeting;

public class App {
    public static void main(String[] args) {
        String who = args.length == 0 ? "Java 11" : args[0];
        System.out.println(Greeting.greet(who));
    }
}
```

Ở ví dụ này, `App.java` là **tệp nguồn khởi chạy**; `Greeting.java` chỉ dùng một lần để **tạo JAR dependency**. Sau khi đóng gói, có thể chạy `App.java` bằng JAR đó mà không cần biên dịch trước `App.java` thành `App.class`.

### Bước 1 — Tạo thư mục đầu ra và đóng gói thư viện

Mở terminal tại thư mục `demo/` (đã chứa hai tệp nguồn như trên). Trên **macOS/Linux**:

```bash
mkdir -p classes lib
javac --release 11 -d classes src/demo/util/Greeting.java
jar --create --file lib/greeting.jar -C classes .
```

Trên **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force classes, lib | Out-Null
javac --release 11 -d classes src/demo/util/Greeting.java
jar --create --file lib/greeting.jar -C classes .
```

- `javac --release 11` biên dịch lớp phụ trợ theo mức Java 11, phù hợp với JDK 11 trở lên.
- `-d classes` đặt `Greeting.class` vào `classes/demo/util/` theo cấu trúc package.
- `jar --create --file ... -C classes .` đóng gói các tệp class vào `lib/greeting.jar`.

Có thể kiểm tra nội dung JAR:

```bash
jar --list --file lib/greeting.jar
```

Trong danh sách phải có `demo/util/Greeting.class`.

### Bước 2 — Chạy trực tiếp `App.java` và khai báo classpath

```bash
java --source 11 --class-path lib/greeting.jar App.java
```

**Kết quả:**

```text
Hello, Java 11!
```

Trong lệnh này, `--source 11` chọn mức ngôn ngữ/API Java 11 cho lần biên dịch ngầm (có thể bỏ qua khi chạy `.java` bằng JDK phù hợp mà không cần chỉ định mức cụ thể). Lệnh chạy trên JDK đang được cài đặt; nó không xuất ra một `App.class` để phân phối.

Thử cú pháp rút gọn và đối số chương trình:

```bash
java -cp "lib/*" App.java Alice
```

**Kết quả:**

```text
Hello, Alice!
```

`"lib/*"` có hiệu lực vì `greeting.jar` ở **ngay trong** thư mục `lib`. Nó đưa tất cả JAR trực tiếp trong thư mục này vào classpath, nhưng **không tìm đệ quy** trong thư mục con.

### Bước 3 — Thử dependency dưới dạng thư mục `.class`

Không nhất thiết phải đóng gói thành JAR. Sau bước `javac -d classes`, có thể chạy:

```bash
java -cp classes App.java Bob
```

**Kết quả:**

```text
Hello, Bob!
```

Classpath phải trỏ tới **thư mục gốc của package** (`classes`); không trỏ tới riêng `classes/demo/util`, vì Java cần tìm `demo/util/Greeting.class` tính từ root đó.

## 4. Nhiều dependency và dấu phân cách theo hệ điều hành

Một classpath có thể gồm nhiều mục: tệp JAR, thư mục chứa `.class` và ký hiệu wildcard cho thư mục JAR.

**macOS/Linux** dùng dấu hai chấm `:` giữa các mục:

```bash
java -cp "lib/*:classes" App.java
```

**Windows (PowerShell hoặc CMD)** dùng dấu chấm phẩy `;`:

```powershell
java -cp "lib/*;classes" App.java
```

Đây là cách viết dành cho trường hợp thư viện nằm trong `lib/` và các lớp tự biên dịch nằm trong `classes/`. Nếu các đường dẫn có dấu cách, hãy bao toàn bộ chuỗi classpath trong dấu ngoặc kép.

Ba chi tiết cần nhớ:

1. Wildcard `lib/*` chỉ lấy các tệp `.jar`/`.JAR` nằm trực tiếp trong `lib`. Nó không thêm toàn bộ thư mục con và không tự lấy `.class` rời ngoài JAR.
2. Khi ghi rõ `-cp`, bạn **thay thế** classpath ứng dụng mặc định/giá trị `CLASSPATH`. Nếu cần tìm các lớp trong thư mục hiện hành, chủ động thêm `.` như một mục, chẳng hạn `-cp ".:lib/*"` trên macOS/Linux hoặc `-cp ".;lib/*"` trên Windows.
3. Đường dẫn tương đối ở classpath được hiểu từ **thư mục làm việc khi chạy lệnh**. Nếu gặp lỗi không tìm thấy thư viện, hãy kiểm tra terminal đang đứng ở đâu và đường dẫn JAR thực tế.

Đối với chương trình đơn giản, dùng `-cp` ngay trên dòng lệnh thường dễ đọc và dễ lặp lại hơn việc phụ thuộc vào biến môi trường `CLASSPATH`.

## 5. Xác định dependency nào thực sự phải có

Khi đọc nguồn Java, cần phân biệt:

- **Lớp thuộc JDK**: `java.lang.String`, `java.util.List`, `java.nio.file.Files`, v.v. nằm trong runtime Java; thông thường không cần thêm JAR vào classpath.
- **Thư viện ngoài JDK**: lớp của Jackson, Commons Lang hoặc thư viện tự viết trong một JAR; cần chuẩn bị đúng dependency và khai báo đường dẫn khi chạy kiểu thủ công.
- **Dependency bắc cầu**: thư viện A sử dụng lớp từ thư viện B; chỉ thêm A có thể chưa đủ nếu B cũng phải có mặt lúc chạy. `-cp` không tải hoặc tự giải quyết dependency bắc cầu.

Ví dụ nếu một thư viện có các JAR cần thiết nằm cùng thư mục `lib`, cách gọi gọn là:

```bash
java -cp "lib/*" App.java
```

Tuy nhiên, wildcard **không kiểm tra xung đột phiên bản** và không đảm bảo thứ tự các JAR khi có các lớp trùng tên. Với ứng dụng có nhiều dependency hoặc quy trình build dài hạn, dùng Maven/Gradle để **quản lý dependency và chạy ứng dụng** phù hợp hơn; launcher nguồn một tệp hữu ích cho bài học, script và thử nghiệm nhỏ.

## 6. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `package demo.util does not exist` hoặc `cannot find symbol` khi chạy `App.java` | Trình biên dịch không thấy lớp từ dependency | Kiểm tra `lib/greeting.jar` có tồn tại, chạy lại với `-cp lib/greeting.jar` **trước** `App.java` |
| `NoClassDefFoundError` khi thực thi | Thiếu lớp cần thiết tại runtime, có thể là dependency bắc cầu | Kiểm tra các JAR cần thiết và phiên bản trong classpath |
| `ClassNotFoundException` khi ứng dụng tự tải lớp bằng tên | Tên lớp hoặc đường dẫn tìm lớp sai | Kiểm tra tên package/lớp, nội dung JAR và cơ chế nạp lớp của ứng dụng |
| `UnsupportedClassVersionError` | Lớp trong JAR được biên dịch cho Java mới hơn JVM đang chạy | Kiểm tra `java -version`, phiên bản thư viện và mức bytecode yêu cầu |
| Chạy `java App.java -cp ...` vẫn báo thiếu lớp | `-cp` nằm sau tệp nguồn nên thành tham số chương trình | Chuyển `-cp ...` lên trước `App.java` |
| `lib/*` không tìm thấy JAR trong thư mục con | Wildcard không tìm đệ quy | Đưa JAR cần thiết về `lib/` hoặc liệt kê đường dẫn cụ thể |

Các lệnh kiểm tra nhanh:

```bash
java -version
javac -version
jar --list --file lib/greeting.jar
```

Trên Windows có thể kiểm tra thư mục làm việc bằng `Get-Location` trong PowerShell; trên macOS/Linux dùng `pwd`. Dùng `jar --list` để xác minh đúng package của lớp, rồi đối chiếu đường dẫn gốc trong classpath.

## 7. Giới hạn và những hiểu nhầm cần tránh

**Classpath không phải trình tải dependency.** Ghi `-cp "lib/*"` không làm Java tải thư viện từ Maven Central; các JAR cần có sẵn trên đĩa. Classpath cũng không giải quyết mâu thuẫn phiên bản dependency.

**Classpath khác module path.** `--class-path` dùng cho cơ chế classpath truyền thống. Nếu chương trình cần các **named modules** và cơ chế Java Platform Module System, hãy xem riêng `--module-path` và các tùy chọn module liên quan. Không tự thay thế `--module-path` bằng `-cp` khi phụ thuộc vào quy tắc module.

**Source-file mode không phải một lệnh build đầy đủ.** JDK biên dịch nguồn khi chạy, nhưng không đảm nhận đóng gói ứng dụng, quản lý version của thư viện hoặc các bước build tùy chỉnh. Annotation processing trong quá trình biên dịch của source-file launcher được tắt; một thư viện cần tạo mã nhờ annotation processor không thể được hỗ trợ đầy đủ chỉ bằng việc thêm JAR vào `-cp`.

**Không nhầm phạm vi tính năng theo phiên bản:** Java 11 đưa vào khả năng chạy trực tiếp chương trình từ một tệp nguồn (JEP 330). Từ **JDK 22**, launcher được mở rộng để tự tìm và biên dịch các tệp nguồn phụ thuộc phù hợp cấu trúc package (JEP 458). Vì vậy không nên phát biểu rằng *mọi Java hiện nay đều chỉ biên dịch đúng một tệp nguồn*. Trong cả hai trường hợp, **việc khai báo JAR/class được biên dịch sẵn bằng classpath vẫn hợp lệ và cần thiết khi ứng dụng sử dụng dependency bên ngoài**.

## 8. Bài tập tự kiểm tra

1. Chạy lại `java -cp lib/greeting.jar App.java` và xác nhận in `Hello, Java 11!`.
2. Chạy `java -cp "lib/*" App.java Minh` và giải thích vì sao in `Hello, Minh!`.
3. Tạm bỏ `-cp`, chạy lại và quan sát lỗi tìm lớp; sau đó khôi phục `-cp`.
4. Dùng `jar --list --file lib/greeting.jar` tìm `demo/util/Greeting.class`, rồi giải thích tại sao mục classpath đúng là `lib/greeting.jar` hoặc `classes`.

## 9. Ghi nhớ

Với chương trình một tệp Java 11+, khai báo dependency dạng JAR bằng `java -cp path/to/library.jar App.java` hoặc `java --class-path "lib/*" App.java`. Khi cần nhiều mục, nối bằng `:` trên macOS/Linux hoặc `;` trên Windows. Classpath phải chỉ đúng JAR hoặc thư mục **gốc** chứa cây package, các tùy chọn JVM phải nằm **trước** `App.java`, và mọi dependency cần thiết phải có sẵn. Ví dụ đã chạy được trên JDK hiện đại bằng cả JAR cụ thể, wildcard và thư mục class.

### Tài liệu tham khảo

- [OpenJDK JEP 330 — Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330)
- [Oracle Java Launcher — `java`, `--class-path` và source-file mode](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Dev.java — Launching Simple Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)
- [OpenJDK JEP 458 — Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
