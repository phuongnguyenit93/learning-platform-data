# Nhận diện lỗi không tìm thấy lớp và không tương thích phiên bản

## 1. Mục tiêu: đọc đúng lỗi trước khi sửa

Một chương trình Java có thể **biên dịch thành công nhưng không khởi động**, hoặc chạy được trên máy phát triển mà thất bại trên máy khác. Hai nhóm nguyên nhân rất phổ biến là:

- **Không tìm thấy lớp:** Java launcher hoặc class loader không tìm được class theo tên và nơi tìm kiếm được cấu hình; hoặc có class chính nhưng thiếu một class phụ thuộc.
- **Không tương thích phiên bản:** bytecode được biên dịch cho mức Java mới hơn JVM đang chạy có thể đọc, gây `UnsupportedClassVersionError`.

Đừng vội sửa mã nghiệp vụ. Trước tiên hãy xác định: lỗi xảy ra lúc **`javac`**, lúc **`java` tìm main class**, hay lúc **JVM nạp một class phụ thuộc**.

~~~mermaid
flowchart TD
    START["Lệnh Java thất bại"] --> PHASE{"Lệnh nào báo lỗi?"}
    PHASE -->|"javac"| BUILD["Kiểm tra mã nguồn,<br/>dependency khi biên dịch"]
    PHASE -->|"java"| MSG{"Thông báo chính?"}
    MSG -->|"Could not find or load main class"| NAME["Tên class, package,<br/>classpath root"]
    MSG -->|"NoClassDefFoundError"| DEP["Thiếu dependency runtime<br/>hoặc lỗi định nghĩa/khởi tạo class"]
    MSG -->|"UnsupportedClassVersionError"| VER["JVM chạy quá cũ<br/>so với class file"]
    MSG -->|"Main method not found"| MAIN["Kiểm tra chữ ký main"]
    NAME --> AGAIN["Sửa đúng nguyên nhân<br/>rồi chạy lại"]
    DEP --> AGAIN
    VER --> AGAIN
    MAIN --> AGAIN
~~~

Các thông báo đầy đủ có thể khác theo JVM và môi trường; sơ đồ là hướng chẩn đoán ban đầu, không phải kết luận dựa vào duy nhất một dòng stack trace.

## 2. Ba nơi dễ bị nhầm: source, bytecode và runtime

| Thành phần | Ví dụ | Công dụng |
|---|---|---|
| Source file | `src/demo/Hello.java` | Đầu vào cho `javac` |
| Class file | `out/demo/Hello.class` | Bytecode JVM có thể nạp |
| Tên class đầy đủ | `demo.Hello` | Tên được chỉ định khi chạy class mode |
| Classpath root | `out` | Nơi JVM bắt đầu tìm đường dẫn `demo/Hello.class` |
| Runtime Java | `java` và JVM đi kèm | Nạp, kiểm tra và thực thi bytecode |
| Compiler | `javac` | Chọn mức ngôn ngữ/API/class file lúc build |

**Quy tắc:** với `package demo;` và `public class Hello`, sau khi biên dịch ra `out/demo/Hello.class`, cách chạy đúng là **`java -cp out demo.Hello`**, không phải `java -cp out Hello` hay `java -cp out/demo demo.Hello`.

Classpath chỉ định **gốc tìm kiếm**, còn package là một phần của **tên định danh class**. Tên tệp `.java` và `.class` không được truyền thay thế tên class trong class mode.

## 3. Dựng một ví dụ chạy đúng trên Java 17+

Tạo cấu trúc sau:

~~~text
classpath-demo/
└── src/
    └── demo/
        └── Hello.java
~~~

Nội dung `src/demo/Hello.java`:

~~~java
package demo;

public final class Hello {
    private Hello() {}

    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name);
    }
}
~~~

Từ thư mục `classpath-demo`, tạo thư mục output, biên dịch, rồi chạy.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
java -cp out demo.Hello
java -cp out demo.Hello Lan
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out .\src\demo\Hello.java
java -cp out demo.Hello
java -cp out demo.Hello Lan
~~~

Kết quả dự kiến từ **hai lệnh chạy**:

~~~text
Hello, Java
Hello, Lan
~~~

Tệp được tạo:

~~~text
out/
└── demo/
    └── Hello.class
~~~

`javac -d out` giữ cấu trúc package trong output. `java -cp out demo.Hello` nạp bytecode tương ứng, rồi gọi `main(String[] args)`.

**Thử lỗi có chủ đích:** chạy `java -cp out Hello`. Launcher tìm `Hello` ở default package, không phải `demo.Hello`, nên thường báo:

~~~text
Error: Could not find or load main class Hello
Caused by: java.lang.ClassNotFoundException: Hello
~~~

Cách sửa là **đổi lệnh chạy** thành `java -cp out demo.Hello`. Không cần đổi tên source, xóa class file hay thêm package lần nữa.

## 4. Lỗi không tìm thấy main class: điều gì cần kiểm tra?

Một lỗi điển hình:

~~~text
Error: Could not find or load main class demo.Hello
Caused by: java.lang.ClassNotFoundException: demo.Hello
~~~

Hãy kiểm tra tuần tự:

1. **Biên dịch có thành công không?** Nếu `javac` báo lỗi, `.class` mới có thể chưa được tạo; tệp bytecode cũ vẫn còn và có thể gây nhầm lẫn.
2. **Class có nằm đúng chỗ?** Với tên `demo.Hello` và classpath `out`, cần có `out/demo/Hello.class`.
3. **Đang đứng trong thư mục nào?** Đường dẫn `out` là tương đối theo thư mục làm việc hiện tại.
4. **Tên class có đầy đủ package không?** `Hello` khác `demo.Hello`; chữ hoa/thường trong tên class cũng quan trọng.
5. **`-cp` có trỏ tới gốc đúng không?** `out/demo` không phải root của class `demo.Hello`.
6. **Có vô tình chạy source mode?** `java Hello.java` có ý nghĩa khác `java Hello` trên các JDK hỗ trợ chạy trực tiếp source.

Lệnh xem file và thư mục hiện hành:

| Bash | PowerShell |
|---|---|
| `pwd` | `Get-Location` |
| `ls out/demo/Hello.class` | `Get-Item .\out\demo\Hello.class` |
| `ls out` | `Get-ChildItem .\out` |

Nếu trình biên dịch và runtime đều tìm thấy class nhưng launcher lại báo thiếu **`main`**, đó là lỗi khác. Với cách chạy class thông thường trên Java 17, điểm vào thường là:

~~~java
public static void main(String[] args) {
    // ...
}
~~~

Class thiếu `main` vẫn có thể biên dịch thành công; nó chỉ không tự trở thành chương trình khởi chạy theo cách này.

## 5. Phân biệt ClassNotFoundException và NoClassDefFoundError

Hai tên trông giống nhau nhưng thường chỉ **những tình huống khác nhau**:

| Lỗi | Ý nghĩa phổ biến | Khi nào gặp? |
|---|---|---|
| `ClassNotFoundException` | Một API tải class **bằng tên**, như `Class.forName` hoặc `ClassLoader.loadClass`, không tìm được class | Nạp động, reflection, hoặc nguyên nhân bên dưới khi launcher không tìm thấy main class |
| `NoClassDefFoundError` | JVM cần định nghĩa/hoàn tất việc sử dụng một class nhưng không có định nghĩa cần thiết, hoặc class trước đó khởi tạo lỗi | Thiếu JAR/class ở runtime, khác biệt classpath hoặc lỗi khởi tạo class |

Ví dụ thiếu class chỉ **khi chạy**:

- Biên dịch `demo.App` có tham chiếu `lib.Helper` khi thư viện `lib.jar` tồn tại trong build classpath.
- Khi chạy, quên đưa `lib.jar` vào runtime classpath.
- JVM cố dùng `lib.Helper` và có thể ném `NoClassDefFoundError: lib/Helper` (thường có `ClassNotFoundException` trong chuỗi nguyên nhân).

**Không giải quyết mọi `NoClassDefFoundError` bằng cách thêm một JAR.** Nếu phần stack trace đề cập `Could not initialize class` hoặc `ExceptionInInitializerError`, class có thể đã được tìm thấy nhưng **static initialization trước đó thất bại**. Khi ấy cần xem lỗi gốc từ static initializer, không chỉ tìm file.

`NoClassDefFoundError` thuộc nhóm `Error`, không phải ngoại lệ nghiệp vụ nên dùng `try/catch` để tiếp tục bình thường. Hướng sửa thông thường là cấu hình đúng và loại bỏ nguyên nhân lỗi khi khởi động.

## 6. Lớp có tồn tại nhưng sai tên package: “wrong name”

Nếu JVM đang tìm `Hello` ở default package nhưng bytecode thực sự chứa tên nhị phân `demo.Hello`, có môi trường hiện lỗi liên quan:

~~~text
java.lang.NoClassDefFoundError: Hello (wrong name: demo/Hello)
~~~

Điều này khác với “không có file”. **File có thể tồn tại** nhưng vị trí và tên class được JVM yêu cầu **không khớp tên định danh bên trong class file**.

Không dùng thủ thuật đổi tên `Hello.class` hay chuyển bừa nó sang thư mục gốc. Hãy xác nhận nội dung `package demo;`, chạy bằng `demo.Hello` và đặt `-cp` vào đúng thư mục root.

Bạn có thể dùng JDK tool:

~~~bash
javap -classpath out demo.Hello
~~~

Nếu lệnh này hiển thị được class `demo.Hello`, nó là bằng chứng rằng `javap` tìm thấy class dưới root `out` theo tên đó (không chứng minh `main` hay toàn bộ dependency runtime đều đúng).

## 7. UnsupportedClassVersionError: bytecode mới, JVM cũ

Ví dụ tình huống:

- Một project được **biên dịch cho Java 17**, tạo class-file major version **61**.
- Bạn cố chạy class ấy bằng **Java 11**, runtime chỉ hỗ trợ class-file major version tối đa **55**.
- JVM có thể báo `UnsupportedClassVersionError`.

Thông báo thường có ý như:

~~~text
java.lang.UnsupportedClassVersionError: demo/Hello
has been compiled by a more recent version of the Java Runtime
(class file version 61.0);
this version of the Java Runtime only recognizes class file versions up to 55.0
~~~

Thông báo có thể khác giữa các JVM; hai con số là ví dụ chuẩn cho Java 17 và Java 11.

Bảng đối chiếu thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

**Không nhầm `javac -version` với `java -version`.** Hai lệnh có thể trỏ tới các JDK/runtime khác nhau nếu máy cài nhiều phiên bản hoặc cấu hình PATH không nhất quán.

Bạn cũng không thể chạy class-file version mới bằng cách **đổi tên file**, sửa package hay thêm `-cp`. Đây là vấn đề tương thích định dạng bytecode/runtime, không phải thiếu đường dẫn.

## 8. Chẩn đoán phiên bản bằng lệnh thật

**Trên Bash:**

~~~bash
java -version
javac -version
type -a java
type -a javac
~~~

**Trên PowerShell:**

~~~powershell
java -version
javac -version
Get-Command java
Get-Command javac
where.exe java
where.exe javac
~~~

Các lệnh này giúp xác minh **lệnh nào được tìm thấy trong PATH**. Trên Windows, `where.exe` khác alias `where` của PowerShell.

Để xem version của `.class`, với demo đã biên dịch:

~~~bash
javap -verbose -classpath out demo.Hello
~~~

Tìm các dòng gần phần đầu:

~~~text
Classfile .../demo/Hello.class
  ...
  major version: 61
~~~

`major version: 61` đúng với class file dành cho Java 17. Đường dẫn và chi tiết khác có thể thay đổi theo nền tảng/JDK.

Nếu đang dùng JDK hỗ trợ Java 17 và cần chạy trên runtime Java 17, biên dịch với:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
~~~

`--release 17` đồng thời chọn mức ngôn ngữ, bytecode target và **các API chuẩn được phép dùng** tương ứng Java 17. Nếu trình biên dịch quá cũ để hỗ trợ release đã yêu cầu, nó sẽ báo lỗi; bạn cần cài JDK phù hợp.

## 9. Ba hướng sửa lỗi phiên bản — chọn theo hoàn cảnh

### Hướng A: Nâng runtime

Nếu môi trường được phép nâng JDK/runtime, chọn runtime **có hỗ trợ class file mới**, đồng thời kiểm thử ứng dụng, thư viện và cấu hình. Đây thường là hướng phù hợp khi project thực sự cần API/tính năng Java mới.

**Không được giả định** nâng runtime là miễn phí rủi ro: framework, flag JVM, bảo mật và dependency native có thể đòi cập nhật.

### Hướng B: Biên dịch cho release cũ hơn

Nếu môi trường bắt buộc chạy Java 17 nhưng bạn đang build bằng JDK 21 (và mã không phụ thuộc tính năng Java 21), thử:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Hello.java
~~~

Mức release yêu cầu phải được **chính phiên bản `javac` đang dùng hỗ trợ**. Với ví dụ này, class file đầu ra sẽ mang major 61. Dùng `javap -verbose` để tự kiểm tra.

Không thể chỉ thay `--release` rồi giữ cú pháp hoặc API chỉ có ở Java mới: compiler sẽ từ chối, và bạn cần refactor mã hoặc chọn runtime mới.

### Hướng C: Đồng bộ môi trường build và runtime

Ghi rõ yêu cầu phiên bản Java vào cấu hình project, CI và hướng dẫn chạy. Nếu build bằng Maven hoặc Gradle, cấu hình Java toolchain và release mục tiêu cho nhất quán. Nếu triển khai container, kiểm tra **base image runtime** thay vì chỉ JDK trên máy phát triển.

Một ứng dụng chạy được trên laptop chưa đủ bằng chứng image/server sẽ chạy được: cần chạy smoke test trên **runtime đích thực tế**.

## 10. Classpath lúc biên dịch khác classpath lúc chạy

Xét ứng dụng phụ thuộc một thư viện JAR. Bạn có thể biên dịch thành công nhờ tham số `-cp` của `javac`, nhưng khi chạy lại quên thư viện ấy trong `java -cp`.

Ví dụ cú pháp, giả sử **`lib/helper.jar` thực sự tồn tại** và chứa các class mà ứng dụng cần:

**Bash trên Linux/macOS:**

~~~bash
javac -cp "lib/helper.jar" -d out src/demo/App.java
java -cp "out:lib/helper.jar" demo.App
~~~

**PowerShell trên Windows:**

~~~powershell
javac -cp "lib/helper.jar" -d out .\src\demo\App.java
java -cp "out;lib/helper.jar" demo.App
~~~

Dấu phân cách nhiều classpath entries là **`:` trên Linux/macOS**, **`;` trên Windows** (phụ thuộc hệ điều hành của JVM, không đơn thuần loại terminal). Đây là ví dụ về **cú pháp**, không phải dự án hoàn chỉnh: class `App` và `helper.jar` phải có sẵn thì lệnh mới chạy được.

Một lỗi khác là thiếu dependency **bắc cầu**: ứng dụng có `library-a.jar` nhưng library A cần thêm library B lúc chạy. Đọc **stack trace tới nguyên nhân sâu nhất**, kiểm tra dependency tree hoặc nội dung JAR, thay vì đoán tên thư viện từ một dòng đầu.

**Lưu ý `java -jar`:** chế độ JAR thực thi có các quy tắc entry point và classpath riêng; `-cp` do bạn chỉ định thường bị bỏ qua khi dùng `-jar`. Khi thiếu dependency, hãy xem manifest, cơ chế đóng gói và tài liệu build của ứng dụng, không áp dụng máy móc cú pháp `java -cp ... Main` vào mọi file JAR.

## 11. Những trường hợp dễ chẩn đoán nhầm

| Triệu chứng | Không nên kết luận ngay | Điều nên xác minh |
|---|---|---|
| `Could not find or load main class` | “Code Java viết sai” | Full class name, classpath root, vị trí `.class` |
| `ClassNotFoundException` | “Luôn thiếu dependency JAR” | Tên lớp được yêu cầu, class loader đang dùng |
| `NoClassDefFoundError` | “Chắc chắn thiếu file” | Có `Caused by`, `wrong name`, `Could not initialize class` không? |
| `UnsupportedClassVersionError` | “Sửa lại source cho đúng cú pháp” | Class-file major vs runtime `java -version` |
| `cannot find symbol` từ `javac` | “Runtime classpath thiếu” | Source/build dependencies ở thời điểm compile |
| `Main method not found` | “Class không tồn tại” | Main class có được tìm thấy nhưng thiếu entry point không? |
| Lỗi xuất hiện chỉ trên server | “Server Java bị hỏng” | JDK/JVM version, container image, PATH, thư mục làm việc, packaging |
| Sau build vẫn in kết quả cũ | “JVM cache nhầm mã” | Có đang chạy class/JAR cũ hoặc output directory khác? |

**Phân biệt thêm:** `ClassNotFoundException` là checked exception khi API tải class theo tên không tìm thấy. `NoClassDefFoundError` là lỗi liên kết/định nghĩa class ở runtime; một lỗi khởi tạo class có thể khiến những lần dùng tiếp theo báo dạng này. Đừng xem hai loại là từ đồng nghĩa.

## 12. Quy trình xử lý sự cố 6 bước

1. **Sao chép đầy đủ lỗi và command** gây lỗi (bao gồm `-cp`, `-jar`, thư mục hiện hành).
2. **Xác định giai đoạn**: `javac`, launcher tìm main class, nạp class phụ thuộc, hay initialization.
3. **Kiểm tra version**: `java -version`, `javac -version`, và `javap -verbose` với class liên quan nếu cần.
4. **Kiểm tra đường đi**: full name, package, classpath root, file `.class`/JAR và đường dẫn tương đối.
5. **Chọn một thay đổi nhỏ nhất**: sửa `-cp`, bổ sung dependency runtime, đồng bộ JDK hoặc đổi `--release`. Không thay đồng thời nhiều yếu tố rồi mất dấu nguyên nhân.
6. **Chạy lại trên môi trường đích**, lưu lệnh hoạt động và thêm kiểm tra smoke test vào hướng dẫn triển khai/CI.

### Ví dụ checklist nhanh cho demo

~~~bash
java -version
javac -version
javap -verbose -classpath out demo.Hello
java -cp out demo.Hello
~~~

Trên PowerShell, bốn lệnh này có cú pháp tương tự. Nếu `javap` không tìm được `demo.Hello`, ưu tiên kiểm tra **output root và tên lớp**. Nếu `javap` hiển thị major 61 nhưng runtime là Java 11, ưu tiên **nâng runtime hoặc build lại với release mà runtime hỗ trợ**.

## 13. Bài tập có đáp án

### Bài A — tìm lỗi classpath

Bạn có `out/demo/Hello.class`, package bên trong là `demo`. Chạy:

~~~bash
java -cp out/demo Hello
~~~

**Đáp án:** classpath root sai cho lớp `demo.Hello`; sửa thành `java -cp out demo.Hello`.

### Bài B — nhận diện lỗi version

Class có `major version: 65`, máy đích dùng JVM Java 17. Lý do có thể thất bại?

**Đáp án:** major 65 là Java 21, Java 17 thông thường chỉ hỗ trợ tới major 61. Có thể xuất hiện `UnsupportedClassVersionError`. Hướng sửa: chạy bằng runtime hỗ trợ Java 21, hoặc biên dịch lại cho release 17 sau khi bảo đảm code/API tương thích.

### Bài C — phân loại lỗi thiếu phụ thuộc

Build có `helper.jar`, lúc chạy quên đưa JAR vào classpath, ứng dụng chỉ lỗi khi gọi một tính năng cụ thể.

**Đáp án:** đây là nghi vấn **thiếu class dependency ở runtime**, có thể báo `NoClassDefFoundError`. Kiểm tra classpath runtime và stack trace; đừng chỉ sửa source hoặc tên main class.

### Bài D — phân biệt hai loại thông báo

1. `java -cp out demo.Hello` báo `Could not find or load main class demo.Hello`.
2. `java -cp out demo.Hello` tìm được class nhưng báo `Main method not found`.

**Đáp án:** (1) xem classpath root/tên đầy đủ/file; (2) xem chữ ký `main` của class đã tìm thấy. Hai trường hợp cần hai cách sửa khác nhau.

### Bài E — build bằng JDK mới, chạy JVM cũ

Bạn build bằng JDK 21, deploy lên Java 17. Nêu ba câu hỏi trước khi sửa.

**Đáp án gợi ý:** (i) class file major version hiện là bao nhiêu? (ii) source và API có tương thích Java 17 không? (iii) được nâng runtime đích hay phải dùng `--release 17`? Sau thay đổi, xác minh bằng `javap` và chạy smoke test trên JVM 17 thực tế.

## 14. Checklist nghiệm thu

- [ ] Phân biệt được **không tìm thấy main class**, **thiếu class phụ thuộc**, **sai tên package**, **không có main** và **không tương thích class-file version**.
- [ ] Biên dịch và chạy ví dụ `demo.Hello` bằng đúng classpath root.
- [ ] Biết `javac` và `java` là hai lệnh có vai trò khác nhau; kiểm tra được cả hai phiên bản.
- [ ] Dùng `javap -verbose` để đọc major version và hiểu 52/55/61/65.
- [ ] Biết Java 17 class (major 61) không chạy được trên JVM Java 11.
- [ ] Phân biệt build classpath và runtime classpath.
- [ ] Biết `java -jar` có cách xử lý classpath khác với class mode.
- [ ] Biết đọc dòng `Caused by` và lỗi initialization trước khi kết luận thiếu JAR.
- [ ] Có thể sửa từng nguyên nhân một và kiểm chứng lại trên runtime đích.

**Kết luận:** khi gặp lỗi Java lúc khởi động, hãy tách ba câu hỏi: **JVM đang tìm class tên nào? Tìm từ classpath root nào? Bytecode có tương thích với JVM đang chạy không?** Trả lời đúng ba câu đó sẽ loại bỏ phần lớn cách sửa mò như đổi tên file, chép JAR ngẫu nhiên hoặc thay phiên bản Java không có căn cứ.