# Chạy lớp bằng java và phân biệt tên lớp với tên tệp

## 1. Điều cần hiểu trước khi gõ lệnh

Trong quy trình Java truyền thống, bạn **viết mã nguồn trong tệp `.java`**, dùng **`javac`** biên dịch mã nguồn thành một hoặc nhiều **tệp `.class`**, rồi dùng lệnh **`java`** để khởi động một lớp có điểm vào chương trình.

~~~mermaid
flowchart LR
    A["Welcome.java<br/>Tên tệp nguồn"] -->|"javac"| B["Welcome.class<br/>Bytecode"]
    B -->|"java Welcome<br/>Tên lớp"| C["JVM nạp lớp<br/>và gọi main"]
    C --> D["Chương trình chạy"]
~~~

**Quy tắc cốt lõi:** trong chế độ chạy **class đã biên dịch**, đối số chính của `java` là **tên lớp (class name)**, thường kèm tên package nếu có. Bạn **không** truyền đường dẫn tệp `.class` như thể đó là chương trình thực thi.

Ví dụ ba lệnh dưới đây không mang cùng ý nghĩa:

| Lệnh | Ý nghĩa |
|---|---|
| `javac Welcome.java` | Biên dịch tệp nguồn `Welcome.java` |
| `java Welcome` | Chạy lớp có tên `Welcome` mà JVM tìm được trên classpath |
| `java Welcome.java` | Chạy **tệp nguồn** bằng source-file mode (có từ Java 11), không phải chạy lớp `Welcome` đã biên dịch theo cách ở dòng trên |

Các ví dụ sử dụng **JDK 17 trở lên**. Hãy mở terminal tại thư mục đúng như ví dụ hoặc điều chỉnh đường dẫn phù hợp với máy của bạn.

## 2. Chạy một lớp đơn giản, không có package

Tạo tệp **`Welcome.java`** với nội dung sau:

~~~java
public class Welcome {
    public static void main(String[] args) {
        String person = args.length > 0 ? args[0] : "Java";
        System.out.println("Xin chao, " + person + "!");
    }
}
~~~

Mở terminal trong thư mục chứa `Welcome.java`. Xác nhận có đủ công cụ của JDK:

~~~bash
java -version
javac -version
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 Welcome.java
java -cp . Welcome
java -cp . Welcome Lan
~~~

Đầu ra của hai lệnh `java`, theo thứ tự:

~~~text
Xin chao, Java!
Xin chao, Lan!
~~~

Giải thích từng thành phần:

- `javac` đọc **`Welcome.java`** và, nếu biên dịch thành công, tạo **`Welcome.class`** trong thư mục hiện hành.
- `--release 17` hướng tới cú pháp/API/class-file tương thích Java 17; trình biên dịch đang dùng phải hỗ trợ mức release này.
- `-encoding UTF-8` chỉ định cách đọc mã nguồn; không bảo đảm terminal hiển thị mọi ký tự Unicode giống nhau.
- `java` là chương trình launcher của runtime; nó khởi động JVM để tìm và thực thi class.
- `-cp .` đặt classpath là thư mục hiện tại; dấu `.` là đường dẫn thư mục, **không phải phần mở rộng tệp**.
- `Welcome` là **tên class**, không phải `Welcome.java` hay `Welcome.class`.
- `Lan` là đối số ứng dụng; với chương trình này nó trở thành `args[0]`.

Nhờ điều kiện `args.length > 0`, chạy không có đối số không gây `ArrayIndexOutOfBoundsException`.

### Lệnh tương ứng trong Bash và PowerShell

Cú pháp `javac` và `java` ở trên **dùng được trong cả Bash và PowerShell**. Ví dụ muốn liệt kê file đầu vào và bytecode đã tạo:

**Bash (Linux/macOS/Git Bash):**

~~~bash
ls Welcome.java
javac --release 17 -encoding UTF-8 Welcome.java
ls Welcome.class
java -cp . Welcome
~~~

**PowerShell (Windows):**

~~~powershell
Get-Item .\Welcome.java
javac --release 17 -encoding UTF-8 .\Welcome.java
Get-Item .\Welcome.class
java -cp . Welcome
~~~

Đường dẫn `.\Welcome.java` dùng khi gọi `javac` là **đường dẫn đến tệp nguồn**. Khi gọi `java` để chạy class, vẫn viết **`Welcome`** vì đó là tên lớp JVM cần tìm.

## 3. Ba tên thường bị nhầm với nhau

| Khái niệm | Ví dụ | Dùng ở đâu? |
|---|---|---|
| **Tên tệp nguồn** | `Welcome.java` | Đối số cho `javac`; editor mở/chỉnh sửa |
| **Tên class đã khai báo** | `Welcome` trong `class Welcome` | Là tên định danh của lớp |
| **Tên tệp bytecode** | `Welcome.class` | Tệp `javac` tạo ra để JVM tải |
| **Tên đầy đủ của class** | `demo.Welcome` | Tên khi lớp thuộc package `demo` |
| **Đường dẫn nguồn** | `src/demo/Welcome.java` | Vị trí tệp trên đĩa |
| **Classpath root** | `out` | Thư mục hoặc tập entry để runtime tìm class |

Không nên suy luận tên class chỉ từ tên tệp. Hãy **đọc khai báo `class` và `package`**, rồi xác định classpath root đang chứa bytecode.

Trong đoạn `public class Welcome` ở ví dụ chính, Java bắt buộc tên tệp nguồn công khai là `Welcome.java`. Trên hệ thống phân biệt chữ hoa/thường, `welcome.java` và `Welcome.java` là những tên khác nhau.

## 4. Khi tên tệp nguồn không phải tên class chạy

Một tệp `.java` có thể chứa nhiều class cấp cao nhất (*top-level class*) miễn tuân thủ quy tắc về class `public`. Tạo tệp **`Examples.java`**:

~~~java
class Helper {
    static String message() {
        return "Hello from Helper";
    }
}

class Runner {
    public static void main(String[] args) {
        System.out.println(Helper.message());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 Examples.java
java -cp . Runner
~~~

Kết quả:

~~~text
Hello from Helper
~~~

`javac` có thể tạo **`Helper.class`** và **`Runner.class`**, mặc dù tệp nguồn tên là **`Examples.java`**. Lý do: không có top-level class nào được khai báo `public`, nên tên tệp nguồn không phải bằng tên `Runner`.

**Lệnh `java -cp . Examples` sẽ không chạy được ví dụ này**, vì không có class tên `Examples`. Thử `java -cp . Runner` mới đúng.

Ngược lại, nếu khai báo `public class Runner`, tệp chứa nó phải được đặt là **`Runner.java`**. Đây là quy tắc biên dịch, không phải quy tắc buộc mọi tên nguồn lúc nào cũng giống tên class chạy.

## 5. Package làm thay đổi tên dùng với lệnh java

Xét cấu trúc dự án:

~~~text
project/
└── src/
    └── demo/
        └── Welcome.java
~~~

Tệp `src/demo/Welcome.java`:

~~~java
package demo;

public class Welcome {
    public static void main(String[] args) {
        String who = args.length > 0 ? args[0] : "Java";
        System.out.println("Xin chao tu demo, " + who + "!");
    }
}
~~~

Phần `package demo;` có nghĩa class có **tên đầy đủ (fully qualified class name)** là `demo.Welcome`, không còn chỉ là `Welcome` ở default package.

Từ thư mục `project`, tạo thư mục kết quả trước khi biên dịch.

**Bash:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/Welcome.java
java -cp out demo.Welcome Lan
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/demo/Welcome.java
java -cp out demo.Welcome Lan
~~~

Kết quả:

~~~text
Xin chao tu demo, Lan!
~~~

Sau biên dịch, cấu trúc quan trọng sẽ là:

~~~text
project/
├── src/
│   └── demo/
│       └── Welcome.java
└── out/
    └── demo/
        └── Welcome.class
~~~

Phân tích lệnh chạy **`java -cp out demo.Welcome Lan`**:

- `-cp out`: nơi JVM bắt đầu tìm các class.
- `demo.Welcome`: class cần chạy, gồm **package + tên lớp**.
- `Lan`: đối số chuyển cho chương trình, không thuộc tên class.

**Classpath phải trỏ tới `out`, không phải `out/demo`**, bởi JVM dùng package `demo` để tìm đường dẫn tương ứng bên dưới classpath root.

~~~mermaid
flowchart TD
    CP["Classpath root: out/"] --> PK["Package: demo/"]
    PK --> BC["Welcome.class"]
    CMD["java -cp out demo.Welcome"] --> CP
~~~

Khi đang ở thư mục `project`, các cách gọi sau là **khác nhau**:

| Lệnh | Đánh giá |
|---|---|
| `java -cp out demo.Welcome` | Đúng |
| `java -cp out Welcome` | Sai tên lớp đầy đủ |
| `java -cp out/demo demo.Welcome` | Sai classpath root |
| `java -cp out/demo Welcome` | Có thể gây lỗi tên class bên trong không khớp đường dẫn/package; không phải cách chạy đúng |
| `java -cp out demo/Welcome.class` | Sai: truyền đường dẫn tệp thay vì tên lớp |

## 6. Điểm vào chương trình: lớp phải có main phù hợp

Trong Java 17, để dùng ví dụ chạy class thông thường như trên, lớp mục tiêu cần phương thức:

~~~java
public static void main(String[] args) {
    // Lệnh bắt đầu từ đây
}
~~~

Một biến thể tương đương có thể dùng `String... args`. Nhưng các phương thức dưới đây **không phải entry point thông thường của Java 17**:

~~~java
// Sai kiểu trả về:
public static int main(String[] args) { return 0; }

// Sai vì thiếu static:
public void main(String[] args) { }

// Sai kiểu tham số:
public static void main(int[] args) { }
~~~

Các class vẫn có thể **biên dịch thành công** nếu những phương thức đó hợp lệ như method thông thường; lỗi xuất hiện khi bạn cố launch chúng làm main class mà không có điểm vào được hỗ trợ.

**Đừng trộn quy tắc Java 17 với các dạng main mới hơn trong những phiên bản Java khác.** Bài này dùng JDK 17 để cú pháp và lệnh có thể đối chiếu nhất quán.

### Main class khác helper class

Một chương trình có thể dùng hàng chục class, nhưng lệnh `java` cần biết **class nào là điểm vào**. Ví dụ `Runner` gọi `Helper.message()`; việc `Helper` không có `main` không ngăn `Runner` chạy. Nhưng chạy `java Helper` như main class sẽ không có entry point phù hợp.

## 7. Phân biệt chế độ chạy class với chạy source trực tiếp

Từ Java 11, launcher còn có **source-file mode**, cho phép chạy trực tiếp một tệp nguồn đơn giản:

~~~bash
java Welcome.java
~~~

Đối chiếu hai cách:

| Cách | Lệnh | Ý nghĩa |
|---|---|---|
| **Class mode** | `javac Welcome.java` rồi `java Welcome` | Bạn biên dịch trước; launcher tìm class đã có trên classpath |
| **Source-file mode** | `java Welcome.java` | Launcher xử lý mã nguồn để thực thi trong lần gọi; không yêu cầu bạn tự tạo `.class` lưu trên đĩa |
| **JAR mode** | `java -jar program.jar` | Launcher dùng thông tin điểm vào của JAR thực thi và quy tắc classpath tương ứng |

Hai lệnh `java Welcome` và `java Welcome.java` khác nhau do **chế độ launcher**, không phải chỉ khác cách viết phần mở rộng. Trong class mode, không ghi `.java` hoặc `.class` theo sau tên lớp.

Source-file mode có những quy tắc biên dịch và tổ chức riêng; nó hữu ích cho thử nhanh ví dụ nhỏ. Khi cần quan sát bytecode, kiểm soát classpath hay mô phỏng quy trình build, nên thực hành `javac` rồi `java` trước.

**Không nhầm `java -jar app.jar` với `java -cp app.jar demo.Welcome`:** chế độ `-jar` dựa vào cấu hình entry point như `Main-Class` trong manifest của JAR; cách dùng `-cp` yêu cầu bạn nêu class để chạy. Không phải file JAR nào cũng tự chạy được bằng `-jar`.

## 8. Classpath không phải đường dẫn đến một file .class riêng lẻ

Classpath là tập **vị trí tìm class và thư viện**. Một entry có thể là thư mục chứa cây package hoặc một file JAR.

Ví dụ có class ứng dụng ở `out/` và thư viện ở `lib/example.jar`:

**Bash (Linux/macOS):**

~~~bash
java -cp "out:lib/example.jar" demo.Welcome
~~~

**PowerShell (Windows):**

~~~powershell
java -cp "out;lib/example.jar" demo.Welcome
~~~

Dấu phân cách các entry của classpath là **`:` trên Linux/macOS** và **`;` trên Windows**; việc dùng Bash hay PowerShell không tự quyết định dấu phân cách, **hệ điều hành chạy JVM** mới là yếu tố. Với Git Bash chạy Java Windows, thông thường vẫn dùng `;`.

Lưu ý: ví dụ `demo.Welcome` ở trên không cần thư viện `example.jar`; đoạn lệnh chỉ minh họa cú pháp nhiều classpath entry, nên chỉ sử dụng khi JAR đó thực sự tồn tại. Lệnh tối thiểu để chạy demo là `java -cp out demo.Welcome`.

Khi chỉ có một entry như `out` hoặc `.`, không cần dấu phân cách nào.

## 9. Các lỗi khi gõ java và cách chẩn đoán

| Thông báo / triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| `Could not find or load main class Welcome` | Sai tên class, sai classpath hoặc chưa biên dịch | Xem `.class` ở đâu, kiểm tra tên `class` và `-cp` |
| `ClassNotFoundException: demo.Welcome` | Class loader không tìm thấy tên class cần nạp | Xem có `out/demo/Welcome.class` và `-cp out` hay không |
| `NoClassDefFoundError` kèm `wrong name` | Tên package trong bytecode không khớp vị trí/kiểu gọi | Kiểm tra khai báo `package`, classpath root và tên đầy đủ |
| `Main method not found` | Class có tồn tại nhưng không có entry point phù hợp | Kiểm tra chữ ký `public static void main(String[] args)` |
| `UnsupportedClassVersionError` | JVM quá cũ để đọc class file đã biên dịch | So sánh `java -version`, mức `--release` và JDK biên dịch |
| Chạy ra kết quả cũ dù đã sửa `.java` | Đang chạy `.class` cũ | Lưu source, chạy lại `javac`, kiểm tra thư mục output |
| `javac` báo tên public class không khớp tên tệp | Tên tệp nguồn sai | Đổi đúng `Welcome.java` cho `public class Welcome` |
| `java` không được nhận diện | JDK/runtime hoặc `PATH` chưa đúng | Kiểm tra cài JDK, cấu hình `PATH`, mở terminal mới |

**Quy trình kiểm tra nhanh khi chạy class mode thất bại:**

1. Đang đứng ở thư mục nào? Bash: `pwd`; PowerShell: `Get-Location`.
2. `javac` đã chạy thành công chưa? Nếu lỗi biên dịch, có thể vẫn còn file `.class` cũ.
3. Class thực tế khai báo `package` nào và `class` nào?
4. Tệp `.class` nằm dưới thư mục classpath nào?
5. Bạn đã gọi **`java -cp <root> package.ClassName`** chưa?
6. Nếu class có nhưng không launch được, kiểm tra chữ ký `main` và `java -version`.

Tránh sửa ngẫu nhiên tên file, package và classpath cùng lúc; hãy xác minh từng điều kiện để biết nguyên nhân thật sự.

## 10. Dùng javap để xác nhận class đã được biên dịch

JDK có `javap` để xem thông tin class file mà không chạy chương trình. Với ví dụ package `demo`:

~~~bash
javap -classpath out demo.Welcome
~~~

Bạn sẽ thấy thông tin của `demo.Welcome`, bao gồm phương thức `public static void main(java.lang.String[])`. Để xem bytecode:

~~~bash
javap -classpath out -c demo.Welcome
~~~

`javap` giúp trả lời “JVM có thể tìm thấy class tên nào, method nào được biên dịch?” nhưng **không thay cho việc thực thi hoặc kiểm thử**. Đầu ra cụ thể thay đổi theo compiler/JDK.

Bạn cũng có thể so sánh sau khi sửa mã nguồn: nếu chưa chạy lại `javac`, `javap` tiếp tục mô tả `.class` cũ ở classpath ấy.

## 11. Các trường hợp biên cần nhớ

**Tên file và tên public class khác nhau.** `public class SalesApp` trong `Program.java` gây lỗi compile. Còn tệp `Program.java` chỉ có `class SalesApp` không public có thể biên dịch thành `SalesApp.class`; lúc chạy dùng `java SalesApp`.

**Package khác thư mục hiện tại.** Với `demo.Welcome`, tên class phải viết đầy đủ khi launch, ngay cả khi bạn đang ở gần tệp `Welcome.class`. Đổi thư mục hiện tại không biến tên đầy đủ của class thành `Welcome`.

**Nhiều class trong cùng một source.** Không có quan hệ “một source luôn tạo một class file”. Nested class còn có cách đặt tên bytecode riêng; hãy để compiler và launcher xử lý thay vì đổi tên `.class` thủ công.

**Tham số ứng dụng đứng sau class name.** `java -cp out demo.Welcome Lan` chuyển `Lan` vào `args`; còn tùy chọn như `-cp out` thuộc về launcher. Đặt sai vị trí có thể khiến chuỗi bị hiểu thành đối số hoặc tên class.

**JVM khác JDK biên dịch.** Nếu máy có nhiều phiên bản Java, `javac -version` và `java -version` có thể khác. Đúng tên class mà sai phiên bản runtime vẫn có thể bị `UnsupportedClassVersionError`.

**Đường dẫn chứa dấu cách.** Bao đường dẫn file/thư mục trong dấu nháy phù hợp của shell:

~~~bash
javac -d "build output" "src/demo/Welcome.java"
java -cp "build output" demo.Welcome
~~~

Trước khi dùng `-d`, hãy tạo thư mục output phù hợp theo môi trường của bạn. Dấu nháy bảo vệ đường dẫn, **không biến tên class thành đường dẫn**.

**Chỉ đổi nội dung source.** Trong class mode, JVM không tự biên dịch lại source bị sửa. Nếu muốn chạy source mới, hãy `javac` lại trước; source-file mode là chế độ khác.

## 12. Bài tập tự kiểm tra có đáp án

### Bài A — chọn đúng lệnh chạy

Có tệp `Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

Bạn đã chạy `javac Hello.java` thành công trong thư mục hiện hành. Lệnh nào chạy **class đã biên dịch**?

A. `java Hello.java`  
B. `java Hello`  
C. `java Hello.class`

**Đáp án:** B. A yêu cầu source-file mode trên runtime hỗ trợ; C dùng đuôi file sai trong class mode.

### Bài B — dự đoán sản phẩm của javac

Tệp nguồn tên `Tools.java`:

~~~java
class Util {
    static int twice(int x) { return x * 2; }
}
class Program {
    public static void main(String[] args) {
        System.out.println(Util.twice(4));
    }
}
~~~

**Câu hỏi:** tạo những class file nào và chạy bằng gì?

**Đáp án:** khi biên dịch thành công, tạo `Util.class` và `Program.class`; chạy `java -cp . Program`, kết quả `8`. Tệp `Tools.java` không tạo class `Tools` vì không có khai báo `class Tools`.

### Bài C — phát hiện classpath root sai

Đã biên dịch `package school;` và `public class Main` thành `out/school/Main.class`. Lệnh nào đúng?

~~~bash
java -cp out school.Main
~~~

**Đáp án:** chính lệnh trên. Không dùng `-cp out/school` hoặc `java -cp out Main`.

### Bài D — truyền tham số đúng vị trí

Từ chương trình `Welcome`, muốn `args[0]` là `Binh`. Hãy viết lệnh.

**Đáp án:** `java -cp . Welcome Binh` với class ở default package và `Welcome.class` trong thư mục hiện tại.

### Bài E — source đã sửa nhưng output chưa thay đổi

Bạn sửa `System.out.println("A");` thành `System.out.println("B");` trong `Welcome.java`, rồi chạy lại `java Welcome` nhưng vẫn thấy `A`.

**Đáp án:** khả năng cao bạn đang chạy `Welcome.class` cũ hoặc một class cùng tên ở classpath khác. Hãy lưu source, chạy lại `javac Welcome.java`, dùng classpath tường minh và xác minh file output.

### Bài F — chẩn đoán “Main method not found”

Tệp `MathTool.java` có:

~~~java
public class MathTool {
    public static int square(int n) {
        return n * n;
    }
}
~~~

**Hỏi:** vì sao `javac MathTool.java` được mà `java MathTool` thất bại?

**Đáp án:** khai báo class và method `square` hợp lệ, nhưng class không có điểm vào `main` phù hợp với chế độ launch Java 17. Thêm `public static void main(String[] args)` để gọi `square` hoặc viết một class `Runner` có main rồi gọi `MathTool.square(3)`.

## 13. Checklist nghiệm thu

- [ ] Biết `javac` nhận **tệp mã nguồn**, còn `java` trong class mode nhận **tên lớp**.
- [ ] Chạy được `javac Welcome.java` và `java -cp . Welcome`.
- [ ] Hiểu quy tắc tên tệp khi class được khai báo `public`.
- [ ] Giải thích được một source có thể biên dịch ra nhiều tệp `.class`.
- [ ] Với `package demo;`, chạy đúng bằng `java -cp out demo.Welcome`.
- [ ] Biết đặt classpath ở **thư mục gốc chứa package**, không ở thư mục con package.
- [ ] Phân biệt `java Welcome` với `java Welcome.java` và `java -jar app.jar`.
- [ ] Xác định được class nào có entry point `main` hợp lệ trong Java 17.
- [ ] Đọc được lỗi class not found, main not found và class file version mismatch.
- [ ] Biết cách xem class đã biên dịch bằng `javap` và kiểm tra hai phiên bản `javac`/`java`.

**Kết luận:** Hãy xác định **class và package trong mã**, **nơi bytecode được biên dịch ra**, rồi mới viết lệnh `java`. Khi chạy class đã biên dịch, dùng `java -cp <classpath-root> package.ClassName` (hoặc chỉ `ClassName` nếu không có package). **Tên tệp `.java` là đầu vào của trình biên dịch; tên class là đối tượng mà launcher cần tìm để chạy.**