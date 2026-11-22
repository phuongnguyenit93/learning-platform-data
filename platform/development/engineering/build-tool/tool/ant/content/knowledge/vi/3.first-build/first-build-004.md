# Biên dịch chương trình Java đầu tiên bằng `javac`

Trước khi sử dụng một công cụ build như Apache Ant, bạn nên hiểu cách Java biên dịch và chạy một chương trình bằng các lệnh cơ bản. Trong bài này, chúng ta sẽ tạo một chương trình Java nhỏ, dùng `javac` để biên dịch mã nguồn thành bytecode, rồi dùng lệnh `java` để chạy chương trình.

Sau bài học, bạn có thể:

- Kiểm tra máy tính đã có bộ công cụ phát triển Java (JDK) hay chưa.
- Tạo một tệp mã nguồn Java có phương thức `main`.
- Biên dịch tệp `.java` bằng `javac` và nhận tệp `.class`.
- Chạy lớp đã biên dịch bằng lệnh `java`.
- Đưa mã nguồn và tệp kết quả vào các thư mục riêng.
- Nhận biết một số lỗi thường gặp khi biên dịch và chạy chương trình.

## 1. Hiểu quá trình biên dịch và chạy Java

Java thường được thực hiện qua hai bước riêng biệt:

1. **Biên dịch:** trình biên dịch `javac` đọc mã nguồn trong tệp `.java`, kiểm tra cú pháp và kiểu dữ liệu, sau đó tạo bytecode trong tệp `.class`.
2. **Chạy:** lệnh `java` khởi động Java Virtual Machine (JVM), nạp bytecode và thực thi chương trình.

Luồng xử lý có thể hình dung như sau:

```text
HelloWorld.java
      |
      | javac HelloWorld.java
      v
HelloWorld.class  (bytecode)
      |
      | java HelloWorld
      v
JVM thực thi chương trình
      |
      v
Xin chao Java!
```

Hai lệnh có nhiệm vụ khác nhau. `javac` tạo ra tệp bytecode; `java` chạy lớp đã được biên dịch. Nếu chỉ biên dịch thành công, chương trình chưa tự động chạy và bạn vẫn cần gọi lệnh `java`.

### JDK, `javac` và `java`

Để biên dịch chương trình, máy tính cần có **Java Development Kit (JDK)**. JDK cung cấp các công cụ phát triển, trong đó có:

- `javac`: trình biên dịch mã nguồn Java.
- `java`: lệnh khởi chạy ứng dụng Java trên JVM.

Vì vậy, nếu máy chỉ có một môi trường chạy Java mà không có trình biên dịch, lệnh `java` có thể hoạt động trong khi `javac` không được tìm thấy. Hãy cài đặt một bản JDK phù hợp với hệ điều hành và yêu cầu của dự án.

## 2. Kiểm tra JDK trên máy tính

Mở Terminal, Command Prompt hoặc PowerShell và chạy:

```bash
java -version
javac -version
```

Nếu JDK đã được cài đặt và cấu hình đúng, cả hai lệnh đều hiển thị thông tin phiên bản. Phiên bản cụ thể phụ thuộc vào JDK bạn đã cài.

Ví dụ, kết quả có thể có dạng:

```text
java version "..."
...
javac ...
```

Không cần kết quả phải giống hệt ví dụ; điều cần kiểm tra là cả `java` và `javac` đều được hệ điều hành tìm thấy.

### Nếu hệ thống không tìm thấy `javac`

Nếu nhận được thông báo như `javac is not recognized` trên Windows hoặc `command not found` trên macOS/Linux, hãy kiểm tra các điểm sau:

1. Đã cài đặt JDK hay mới chỉ cài một môi trường chạy Java.
2. Thư mục `bin` bên trong thư mục cài JDK đã được thêm vào biến môi trường `PATH` chưa.
3. Sau khi thay đổi biến môi trường, bạn đã mở một cửa sổ Terminal mới chưa.

`PATH` giúp hệ điều hành tìm các chương trình như `java` và `javac` khi bạn gõ lệnh. Một số công cụ còn sử dụng biến `JAVA_HOME` để xác định thư mục gốc của JDK. Nếu cấu hình `JAVA_HOME`, giá trị thường trỏ đến thư mục JDK; `PATH` cần chứa thư mục `bin` của JDK đó.

Trên Windows, có thể dùng lệnh sau để xem đường dẫn mà hệ thống tìm thấy:

```powershell
where.exe java
where.exe javac
```

Trên macOS hoặc Linux:

```bash
which java
which javac
```

Nếu các lệnh trên không trả về đường dẫn hợp lệ, hãy sửa cài đặt JDK hoặc `PATH`, sau đó mở Terminal mới và kiểm tra lại.

## 3. Tạo chương trình Java đầu tiên

Tạo một thư mục làm việc, ví dụ `first-java`. Bên trong thư mục đó, tạo tệp có tên chính xác là `HelloWorld.java`.

Nội dung tệp:

```java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Xin chao Java!");
    }
}
```

Lưu tệp với mã hóa UTF-8. Trong ví dụ này, chuỗi in ra dùng ký tự không dấu để tập trung vào các bước biên dịch đầu tiên; bạn có thể thay bằng một câu tiếng Việt có dấu sau khi đã cấu hình mã hóa phù hợp.

### Đọc cấu trúc chương trình

- `public class HelloWorld` khai báo một lớp có tên `HelloWorld`. Tên lớp công khai phải trùng với tên tệp, bao gồm cả chữ hoa và chữ thường: `HelloWorld.java`.
- `public static void main(String[] args)` khai báo điểm bắt đầu mà trình khởi chạy Java tìm để thực thi ứng dụng dạng này.
- `System.out.println(...)` in nội dung ra đầu ra chuẩn và xuống dòng sau khi in.
- Dấu `{` và `}` xác định phạm vi của lớp và phương thức; dấu `;` kết thúc câu lệnh Java.

Tên tệp và tên lớp phân biệt chữ hoa, chữ thường. `HelloWorld.java`, `Helloworld.java` và `helloWorld.java` là các tên khác nhau trên nhiều hệ thống tệp. Hãy giữ đúng cách viết `HelloWorld` trong cả tên tệp lẫn tên lớp.

## 4. Biên dịch bằng `javac`

Mở Terminal tại thư mục chứa `HelloWorld.java`. Kiểm tra vị trí hiện tại nếu cần, rồi chạy:

```bash
javac HelloWorld.java
```

Nếu mã nguồn hợp lệ, lệnh thường kết thúc mà không in thông báo thành công. Một tệp mới tên `HelloWorld.class` sẽ xuất hiện trong cùng thư mục.

Sau khi biên dịch, thư mục có dạng:

```text
first-java/
├── HelloWorld.java
└── HelloWorld.class
```

`HelloWorld.java` là mã nguồn mà bạn viết. `HelloWorld.class` chứa bytecode do trình biên dịch tạo ra. Bạn thường không cần mở hoặc chỉnh sửa tệp `.class` bằng tay.

Nếu có lỗi cú pháp hoặc lỗi biên dịch, `javac` sẽ hiển thị thông báo kèm vị trí gần nơi phát hiện lỗi. Hãy đọc tên tệp, số dòng và nội dung thông báo, sửa mã nguồn rồi chạy lại lệnh biên dịch.

## 5. Chạy chương trình bằng `java`

Sau khi biên dịch thành công, vẫn ở thư mục chứa `HelloWorld.class`, chạy:

```bash
java HelloWorld
```

Kết quả mong đợi:

```text
Xin chao Java!
```

Khi chạy, hãy ghi nhớ:

- Gõ tên lớp `HelloWorld`, không thêm phần mở rộng `.class`.
- Lệnh `java` cần tìm thấy lớp đã biên dịch thông qua classpath.
- Khi không chỉ định classpath, Java thường sử dụng thư mục hiện tại làm classpath mặc định.

Vì vậy, với ví dụ đơn giản này, chạy lệnh từ thư mục chứa `HelloWorld.class` là đủ.

## 6. Tách mã nguồn và kết quả biên dịch

Khi dự án lớn hơn, không nên để tệp `.class` nằm lẫn với mã nguồn. Ta có thể đặt mã nguồn trong `src` và kết quả biên dịch trong `out`.

Tạo cấu trúc thư mục:

```text
first-java/
├── src/
│   └── HelloWorld.java
└── out/
```

Mở Terminal tại thư mục `first-java`, sau đó biên dịch:

```bash
javac -encoding UTF-8 -d out src/HelloWorld.java
```

Ý nghĩa các phần của lệnh:

- `javac` gọi trình biên dịch Java.
- `-encoding UTF-8` chỉ định mã hóa ký tự của tệp mã nguồn.
- `-d out` yêu cầu trình biên dịch đặt các tệp `.class` vào thư mục `out`.
- `src/HelloWorld.java` là đường dẫn đến tệp nguồn cần biên dịch.

Sau khi biên dịch, cấu trúc thư mục sẽ là:

```text
first-java/
├── src/
│   └── HelloWorld.java
└── out/
    └── HelloWorld.class
```

Chạy chương trình bằng cách chỉ định classpath:

```bash
java -cp out HelloWorld
```

Ở đây, `-cp` là viết tắt của `-classpath`; giá trị `out` cho Java biết nơi tìm các lớp đã biên dịch. Tên lớp vẫn là `HelloWorld`, không phải `out.HelloWorld` vì ví dụ này chưa khai báo package.

Trên Windows, dấu phân cách giữa nhiều mục classpath là dấu chấm phẩy (`;`). Trên macOS và Linux, dấu phân cách là dấu hai chấm (`:`). Ví dụ khi cần thêm hai thư mục vào classpath:

```powershell
java -cp "out;lib/example.jar" HelloWorld
```

```bash
java -cp "out:lib/example.jar" HelloWorld
```

Bạn chưa cần thêm thư viện ở bài đầu tiên; hai ví dụ này chỉ minh họa cách classpath được mở rộng khi dự án cần thư viện bên ngoài.

## 7. Biên dịch nhiều tệp nguồn

Một chương trình Java có thể gồm nhiều lớp nằm trong các tệp nguồn khác nhau. Khi các lớp phụ thuộc lẫn nhau, bạn có thể truyền nhiều tệp `.java` cho `javac` trong cùng một lệnh.

Ví dụ, tạo hai tệp trong thư mục `src`.

Tệp `src/Greeter.java`:

```java
public class Greeter {
    public String message() {
        return "Xin chao tu lop Greeter!";
    }
}
```

Tệp `src/HelloWorld.java`:

```java
public class HelloWorld {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.message());
    }
}
```

Biên dịch cả hai tệp:

```bash
javac -encoding UTF-8 -d out src/Greeter.java src/HelloWorld.java
```

Chạy lớp có phương thức `main`:

```bash
java -cp out HelloWorld
```

Kết quả:

```text
Xin chao tu lop Greeter!
```

Sau khi biên dịch, thư mục `out` chứa cả `Greeter.class` và `HelloWorld.class`. Khi chạy `HelloWorld`, JVM có thể nạp lớp `Greeter` từ cùng classpath `out` khi chương trình cần đến lớp đó.

## 8. Một số lỗi thường gặp

| Thông báo hoặc hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac is not recognized` hoặc `command not found` | Chưa cài JDK hoặc `PATH` chưa trỏ đến thư mục `bin` của JDK. | Cài JDK, kiểm tra `PATH`, mở Terminal mới và chạy lại `javac -version`. |
| `error: file not found: HelloWorld.java` | Terminal đang ở sai thư mục hoặc tên tệp bị gõ sai. | Chuyển đến thư mục chứa tệp và kiểm tra chính xác tên, chữ hoa, chữ thường. |
| `class HelloWorld is public, should be declared in a file named HelloWorld.java` | Tên lớp `public` không khớp tên tệp. | Đổi tên tệp hoặc lớp để chúng khớp nhau. |
| `Could not find or load main class HelloWorld` | Java không tìm thấy lớp trên classpath, hoặc tên lớp được nhập sai. | Kiểm tra vị trí tệp `.class`; dùng `java -cp out HelloWorld` nếu lớp nằm trong `out`. |
| `Main method not found` | Lớp không có phương thức `main` đúng chữ ký hoặc bạn chạy nhầm lớp. | Kiểm tra khai báo `public static void main(String[] args)` và chạy đúng tên lớp. |
| `UnsupportedClassVersionError` | Lớp được biên dịch bằng phiên bản Java mới hơn phiên bản JVM đang dùng để chạy. | Dùng JDK/JVM tương thích hoặc biên dịch với mức phiên bản mục tiêu phù hợp. |

Một lỗi khác có thể xuất hiện khi chương trình dùng ký tự ngoài ASCII. Nếu ký tự trong mã nguồn bị đọc sai, hãy lưu tệp bằng UTF-8 và biên dịch với tùy chọn `-encoding UTF-8`.

Khi gặp lỗi, hãy phân biệt lỗi biên dịch và lỗi chạy:

- Nếu `javac` báo lỗi, hãy sửa mã nguồn hoặc lệnh biên dịch trước. Có thể chưa có tệp `.class` mới.
- Nếu `javac` thành công nhưng `java` báo lỗi, hãy kiểm tra classpath, tên lớp, phương thức `main` và phiên bản JVM.
- Nếu chương trình chạy nhưng kết quả không như mong muốn, hãy kiểm tra logic trong mã nguồn. Đây có thể là lỗi chương trình chứ không phải lỗi biên dịch.

## 9. Các tùy chọn `javac` hữu ích

Trong những bài đầu, bạn chỉ cần một vài tùy chọn cơ bản:

| Tùy chọn | Công dụng | Ví dụ |
|---|---|---|
| `-d` | Chọn thư mục lưu các tệp `.class`. | `javac -d out src/HelloWorld.java` |
| `-cp` hoặc `-classpath` | Chỉ định nơi tìm các lớp và thư viện cần cho quá trình biên dịch. | `javac -cp "lib/example.jar" -d out src/HelloWorld.java` |
| `-encoding` | Chỉ định mã hóa của tệp nguồn. | `javac -encoding UTF-8 HelloWorld.java` |
| `-version` | Hiển thị phiên bản trình biên dịch. | `javac -version` |
| `-help` | Hiển thị trợ giúp về các tùy chọn. | `javac -help` |

Classpath của trình biên dịch và classpath lúc chạy có liên quan nhưng phục vụ hai thời điểm khác nhau. `javac -cp ...` giúp trình biên dịch tìm các lớp cần thiết khi biên dịch; `java -cp ...` giúp JVM tìm các lớp khi chạy. Nếu ứng dụng cần thư viện bên ngoài, thư viện phù hợp phải có mặt ở cả hai bước.

## 10. Từ `javac` đến Apache Ant

Đến đây, bạn đã thực hiện thủ công các thao tác chính của một quy trình build nhỏ: xác định mã nguồn, biên dịch và đặt kết quả vào thư mục đầu ra. Với một dự án có nhiều tệp, thư viện và bước xử lý, việc gõ lại nhiều lệnh sẽ mất thời gian và dễ sai.

Apache Ant cho phép mô tả các bước đó trong tệp `build.xml`. Ant có task `<javac>` để gọi trình biên dịch Java. Ví dụ tối giản:

```xml
<project name="first-java" default="compile">
    <property name="src.dir" value="src" />
    <property name="build.dir" value="out" />

    <target name="compile">
        <mkdir dir="${build.dir}" />
        <javac
            srcdir="${src.dir}"
            destdir="${build.dir}"
            encoding="UTF-8"
            includeantruntime="false" />
    </target>
</project>
```

Trong ví dụ này:

- `src.dir` xác định thư mục chứa mã nguồn.
- `build.dir` xác định thư mục nhận các tệp đã biên dịch.
- `<mkdir>` tạo thư mục đầu ra nếu thư mục đó chưa tồn tại.
- `<javac>` thực hiện công việc tương tự lệnh `javac -encoding UTF-8 -d out ...` mà bạn vừa chạy thủ công.
- `default="compile"` cho biết target mặc định khi chạy Ant mà không chỉ định target khác.

Đây là ví dụ để thấy mối liên hệ giữa lệnh `javac` và task `<javac>` của Ant. Để chạy được tệp build, máy cần cài Ant và JDK, đồng thời cấu hình môi trường phù hợp. Các bài tiếp theo có thể mở rộng tệp `build.xml` với những target như `clean`, `compile` và `run`.

## 11. Bài thực hành

Thực hiện lại quy trình mà không sao chép nguyên văn từng lệnh:

1. Tạo thư mục `first-java/src` và `first-java/out`.
2. Tạo lớp `HelloWorld` trong `src/HelloWorld.java`.
3. Thay nội dung in ra bằng một lời chào có tên của bạn.
4. Biên dịch với `javac -encoding UTF-8 -d out src/HelloWorld.java`.
5. Chạy bằng `java -cp out HelloWorld`.
6. Tạo thêm lớp `Greeter`, gọi lớp đó từ `HelloWorld`, rồi biên dịch cả hai tệp.

Nếu muốn tự kiểm tra kết quả, hãy trả lời các câu hỏi sau:

- Lệnh nào tạo ra tệp `.class`?
- Lệnh nào khởi chạy chương trình?
- Tùy chọn `-d` dùng để làm gì?
- Vì sao khi chạy `java -cp out HelloWorld`, ta chỉ ghi tên lớp mà không ghi `HelloWorld.class`?
- Nếu biên dịch thành công nhưng không chạy được lớp, bạn sẽ kiểm tra những thông tin nào?

## Kết luận

`javac` là công cụ dùng để biên dịch mã nguồn Java thành bytecode; `java` dùng JVM để chạy bytecode đó. Hãy nắm chắc quy trình tạo tệp `.java`, biên dịch thành `.class`, rồi chạy lớp bằng classpath. Đây là nền tảng để hiểu cách Apache Ant và các công cụ build khác tự động hóa quá trình biên dịch trong những dự án Java lớn hơn.
