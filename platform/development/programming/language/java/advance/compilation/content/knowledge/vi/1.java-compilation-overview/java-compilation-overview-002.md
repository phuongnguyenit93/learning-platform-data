# Từ mã nguồn Java đến tệp .class và chương trình chạy

Một tệp `.java` là mã nguồn để con người viết và đọc. Trình biên dịch Java (`javac`) chuyển mã nguồn hợp lệ thành các tệp `.class` chứa **bytecode Java** và thông tin cấu trúc lớp. Khi chạy chương trình, lệnh `java` khởi động JVM, nạp các lớp cần thiết, kiểm tra và liên kết chúng, khởi tạo lớp, rồi thực thi bytecode (thông qua thông dịch, biên dịch JIT hoặc kết hợp tùy JVM). Hai thời điểm **biên dịch** và **chạy** vì vậy khác nhau: biên dịch thành công không đảm bảo mọi phụ thuộc, cấu hình hoặc điều kiện khi chạy đều đúng.

Bài học theo dõi đường đi từ mã nguồn, tệp class đến chương trình thực thi; phân biệt công việc của `javac`, công cụ `java` và JVM, đồng thời hướng dẫn các lệnh kiểm chứng trên Java 17 trở lên.

## 1. Sơ đồ tổng quan

```text
Mã nguồn Hello.java
        |
        v
  javac (biên dịch)
  - phân tích cú pháp
  - phân giải tên và kiểm tra kiểu
  - tạo bytecode, metadata
        |
        v
    Hello.class                 (không phải mã máy gốc)
        |
        v
  java -cp out Hello
        |
        v
       JVM
  - nạp class
  - xác minh bytecode, liên kết
  - khởi tạo class theo nhu cầu
  - tìm và gọi main
  - thực thi; có thể tối ưu bằng JIT
        |
        v
  Kết quả, lỗi hoặc tác dụng của chương trình
```

Đây là **mô hình khái quát**, không phải lời cam kết rằng mọi pha đều diễn ra tuần tự cho mọi lớp. JVM có thể nạp hoặc phân giải tham chiếu theo nhu cầu; chi tiết thực thi và thời điểm JIT phụ thuộc JVM. Trong một lệnh chạy thông thường, việc khởi tạo lớp chứa phương thức `main` xảy ra trước khi gọi `main`.

Các khái niệm cần phân biệt:

| Thành phần | Vai trò | Kết quả/vị trí |
| --- | --- | --- |
| Mã nguồn `.java` | Mô tả lớp, giao diện, bản ghi, biểu thức, câu lệnh… bằng ngôn ngữ Java | Tệp văn bản, đầu vào của `javac` |
| `javac` | Phân tích, kiểm tra hợp lệ và phát sinh bytecode | Một hay nhiều tệp `.class`; hoặc thông báo lỗi biên dịch |
| Tệp `.class` | Định dạng nhị phân Java Class File chứa bytecode, constant pool và metadata | Đầu vào có thể được JVM/ClassLoader đọc |
| `java` | Công cụ khởi động môi trường thực thi Java và lớp/module/nguồn được yêu cầu | Tiến trình JVM và ứng dụng |
| JVM | Định nghĩa mô hình thực thi, nạp/liên kết/khởi tạo lớp và chạy bytecode | Hành vi khi chạy; có thể sinh lỗi hoặc ngoại lệ |

`javac` thường **không** tạo trực tiếp một tệp thực thi máy như `.exe`. Bytecode có tính độc lập tương đối với hệ điều hành và CPU; JVM phù hợp với môi trường là thành phần cung cấp cách thực thi. Điều này không có nghĩa mọi ứng dụng tự động chạy ở mọi nơi: phiên bản Java, thư viện, JNI, file, quyền truy cập và cấu hình hệ thống vẫn ảnh hưởng.

## 2. Thực hành tối thiểu: Hello.java → Hello.class → stdout

Tạo một file tên `Hello.java` với nội dung:

```java
public class Hello {
    public static void main(String[] args) {
        String target = "Java";
        System.out.println("Xin chào, " + target + "!");
    }
}
```

Tại thư mục chứa `Hello.java`, chạy với JDK 17+:

```bash
javac -encoding UTF-8 -d out Hello.java
java -cp out Hello
```

Kết quả stdout của lệnh `java`:

```text
Xin chào, Java!
```

Điều quan sát được:

1. `javac` kiểm tra mã nguồn; nếu hợp lệ, nó tạo `out/Hello.class`. Tùy hệ điều hành, dấu phân cách đường dẫn có thể là `/` hoặc `\`.
2. `-encoding UTF-8` chỉ định cách `javac` đọc các ký tự nguồn, giúp ví dụ tiếng Việt ít phụ thuộc cấu hình mã hóa mặc định.
3. `-d out` chọn thư mục gốc để đặt tệp class. Với lớp không khai báo `package`, kết quả nằm ngay trong `out`. Nên tạo thư mục đầu ra riêng để tránh trộn mã nguồn và sản phẩm biên dịch.
4. `java -cp out Hello` đặt thư mục `out` trên **classpath** và yêu cầu chạy lớp tên `Hello`. Lệnh dùng **tên lớp** chứ không ghi `Hello.class` hay đường dẫn `out/Hello.class`.
5. Trong chương trình này, JVM tìm phương thức khởi động `public static void main(String[] args)`, rồi câu lệnh `println` in một dòng ra stdout.

Nếu thiếu JDK, hệ thống có thể không tìm thấy `javac`. JRE/runtime có thể chạy ứng dụng nhưng không nhất thiết cung cấp trình biên dịch. `java -version` cho biết runtime đang dùng; `javac -version` cho biết phiên bản trình biên dịch. Nếu nhiều JDK được cài, hai lệnh có thể trỏ tới các bản khác nhau do `PATH`/cấu hình môi trường.

### Tên file và kiểu khai báo

Trong ví dụ, `Hello` là một `public` top-level class, vì vậy file nguồn phải là `Hello.java` (phân biệt chữ hoa/chữ thường theo quy tắc tên Java). Một tệp nguồn có thể khai báo nhiều top-level type không phải `public` và có thể sinh nhiều tệp `.class`; các nested, local hoặc anonymous class cũng có thể tạo thêm class file. **Không nên đồng nhất “một file nguồn = một file class”.**

## 3. Bên trong quá trình biên dịch của javac

Ở mức học tập, có thể mô tả các bước sau:

| Giai đoạn | Trình biên dịch làm gì? | Ví dụ lỗi hoặc kết quả |
| --- | --- | --- |
| Đọc nguồn và phân tích từ vựng/cú pháp | Nhận diện token, cấu trúc khai báo, biểu thức và câu lệnh; xây dựng biểu diễn cú pháp | Thiếu dấu `;`, thiếu dấu `}`, cú pháp `if` không hợp lệ |
| Phân giải tên và symbol | Xác định `String`, `System`, biến `target`, phương thức được gọi thuộc khai báo nào | `cannot find symbol` khi tham chiếu tên không tồn tại/không hiển thị |
| Kiểm tra kiểu và ràng buộc ngôn ngữ | Kiểm tra kiểu gán, lời gọi, quyền truy cập, phương thức, generic, checked exception… | Không thể gán `String` cho `int` |
| Hạ cấp/biến đổi biểu diễn | Chuyển một số cấu trúc nguồn sang dạng phù hợp bytecode, có thể tạo mã hỗ trợ | Một số cấu trúc generic bị xóa kiểu (erasure); biểu thức lambda được thể hiện qua cơ chế bytecode/runtime |
| Phát sinh class file | Ghi định dạng class file, bytecode các phương thức, bảng hằng và thuộc tính | `Hello.class` và các class file liên quan |

Đây không phải danh sách đầy đủ các pass nội bộ của từng phiên bản `javac`. Trong thực tế, trình biên dịch có thể thực hiện nhiều pha và tối ưu/biến đổi khác nhau.

Ví dụ sau **cố ý không biên dịch được**:

```java
public class Broken {
    public static void main(String[] args) {
        int count = "5";
    }
}
```

Lưu là `Broken.java` rồi chạy `javac Broken.java`: trình biên dịch báo lỗi kiểu vì không thể chuyển `String` thành `int`. Đừng coi các dòng lỗi và số cột thông báo là bất biến giữa các phiên bản. Khi có lỗi biên dịch, không được giả định rằng một `Broken.class` mới hợp lệ đã được tạo.

Tương tự, `javac` không chạy phương thức `main` chỉ để xem kết quả. Nó kiểm tra điều kiện có thể kiểm tra từ mã nguồn và các phụ thuộc có sẵn. Ví dụ phép chia cho biến bằng 0, thao tác file hoặc kết nối mạng có thể chỉ thất bại lúc thực thi.

### Lời gọi phương thức và thông tin kiểu

Với một lời gọi như `System.out.println(...)`, mã nguồn dùng tên và khai báo; bytecode thường giữ **tham chiếu ký hiệu** đến lớp, field và phương thức trong constant pool. JVM sẽ phân giải các tham chiếu này thành thực thể runtime theo quy tắc liên kết, có thể theo nhu cầu. Do đó một tệp `.class` chứa nhiều thông tin hơn chuỗi lệnh đơn giản.

`javac` cũng không cam kết “tối ưu hết” mọi phép tính. JVM có thể thực hiện tối ưu runtime dựa trên thông tin quan sát được, còn trình biên dịch có thể gấp hằng, hạ cấp cấu trúc ngôn ngữ và phát sinh chỉ thị phù hợp.

## 4. Class file và bytecode trông như thế nào?

`.class` là **tệp nhị phân**, không phải file văn bản nên không đọc trực tiếp bằng editor như `.java`. Theo định dạng class file, nó có phần nhận dạng, phiên bản, constant pool, khai báo class, field, method và các thuộc tính. Phương thức có bytecode thông thường mang nội dung trong thuộc tính `Code`; không phải phương thức nào cũng có thân bytecode (ví dụ phương thức `abstract` hoặc `native`).

Có thể khảo sát bằng công cụ đi cùng JDK:

```bash
javap -classpath out Hello
javap -classpath out -c Hello
javap -classpath out -v Hello
```

- `javap Hello` (với classpath phù hợp) hiển thị khai báo các member ở mức bytecode.
- `-c` hiển thị các instruction như tải giá trị, gọi phương thức, trả về; nội dung chính xác phụ thuộc mã nguồn, phiên bản trình biên dịch và cấu trúc Java.
- `-v` hiển thị thông tin chi tiết như version, constant pool, flag và các thuộc tính; đầu ra dài nên chỉ dùng khi cần phân tích.

**Không suy luận trực tiếp mã nguồn ban đầu từ bytecode.** Tên biến cục bộ, bình luận và một phần cấu trúc nguồn có thể không được giữ lại; cùng hành vi có thể được biên dịch thành bytecode khác nhau. `javap` là công cụ đọc class file, không phải máy chạy ứng dụng.

### Phiên bản class file

Class file mang cặp phiên bản `major/minor` cho biết mức định dạng mà runtime phải hỗ trợ. Với class file Java 17 thông thường, `major version` là **61**. Một JVM chỉ hỗ trợ class file thấp hơn có thể ném `UnsupportedClassVersionError` khi cố nạp bản mới hơn. Đây là một ví dụ điển hình của “biên dịch thành công trên máy A nhưng không chạy được trên máy B”.

Để chủ động nhắm đến Java 17 khi dùng JDK mới hơn, sử dụng:

```bash
javac --release 17 -encoding UTF-8 -d out Hello.java
```

`--release 17` nhắm tới mức ngôn ngữ, bytecode và API Java SE phù hợp với release đó. Nó không tự đóng gói thư viện ngoài; một ứng dụng vẫn cần các thư viện runtime của chính nó và môi trường tương thích. Với toolchain chỉ có JDK 17, `--release 17` cũng hợp lệ.

## 5. Từ classpath đến package và tên lớp đầy đủ

Một lớp đặt trong package phải được gọi theo **tên đầy đủ**. Giả sử file `src/com/example/app/Main.java` chứa:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Ứng dụng đang chạy");
    }
}
```

Tại thư mục dự án, chạy:

```bash
javac -encoding UTF-8 -d out src/com/example/app/Main.java
java -cp out com.example.app.Main
```

Stdout:

```text
Ứng dụng đang chạy
```

`javac -d out` đặt class theo package vào `out/com/example/app/Main.class`. Còn `-cp out` trỏ tới **gốc của cây package**, không trỏ tới chính thư mục `out/com/example/app`. Khi dùng `java`, viết `com.example.app.Main` thay vì chỉ `Main` hoặc `Main.class`.

**Classpath** là danh sách vị trí để class loader hỗ trợ tìm lớp và resource (ví dụ thư mục, JAR). Với một ứng dụng dùng thư viện khác, cả quá trình biên dịch và chạy có thể cần classpath thích hợp. Ví dụ ký hiệu sau cần thay `lib/example.jar` bằng JAR có thật và thay file nguồn, lớp khởi chạy cho khớp dự án:

```bash
javac -cp lib/example.jar -d out src/com/example/app/Main.java
java -cp "out:lib/example.jar" com.example.app.Main
```

Dấu phân cách nhiều mục classpath là **`:` trên Linux/macOS và `;` trên Windows**. Vì vậy dòng `java` minh họa trên áp dụng cho Linux/macOS; ở Windows dùng `"out;lib/example.jar"`. Trên cả hai hệ điều hành, dấu ngoặc kép có ích khi đường dẫn chứa khoảng trắng.

**Module path** (`--module-path`) của JPMS khác classpath; ứng dụng module dùng tên module, mô tả `module-info.java` và có quy tắc đọc/xuất package riêng. Không tự thay classpath bằng module path nếu chương trình chưa được thiết kế thành module. Từ ví dụ cơ bản này, hãy nắm chính xác ý nghĩa của `-d`, `-cp` và tên lớp trước.

## 6. JVM làm gì khi chương trình bắt đầu chạy?

Với chương trình classpath truyền thống, lệnh `java -cp out Hello` khởi động một JVM và yêu cầu chạy lớp `Hello`. JVM thực hiện các hoạt động sau theo đặc tả và nhu cầu chương trình:

1. **Loading (nạp lớp):** class loader tìm định nghĩa lớp và xây dựng biểu diễn `Class` runtime. Không phải tất cả các lớp trong thư mục classpath đều được nạp ngay từ đầu.
2. **Linking (liên kết):** bao gồm verification (kiểm tra tính hợp lệ/giới hạn an toàn của class file), preparation (chuẩn bị các trường `static` với giá trị mặc định và cấu trúc runtime cần thiết), và resolution (phân giải tham chiếu ký hiệu). Resolution có thể được thực hiện muộn tùy tham chiếu và JVM; không nên tưởng tượng luôn có một lượt phân giải tất cả trước `main`.
3. **Initialization (khởi tạo):** thực hiện các static field initializer và static initializer block theo thứ tự được quy định khi lớp cần được khởi tạo; bước này khác với preparation. Những lớp khác có thể được khởi tạo về sau.
4. **Execution (thực thi):** bắt đầu luồng gọi `main` và những phương thức ứng dụng cần đến. JVM thực hiện bytecode qua interpreter, JIT hoặc cơ chế thực thi khác tuân đặc tả. HotSpot thường có cơ chế biên dịch JIT cho code được chạy thường xuyên, nhưng không có bảo đảm mọi phương thức được JIT.

Ví dụ nhỏ về khởi tạo lớp, tạo file `Lifecycle.java`:

```java
public class Lifecycle {
    static {
        System.out.println("Khởi tạo lớp");
    }

    public static void main(String[] args) {
        System.out.println("Chạy main");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Lifecycle.java
java Lifecycle
```

Stdout:

```text
Khởi tạo lớp
Chạy main
```

Lệnh `javac` không in hai dòng trên vì nó chỉ biên dịch. Khối `static` được thực thi khi JVM khởi tạo lớp `Lifecycle`; sau đó `main` mới in dòng còn lại. Các khởi tạo static trong ứng dụng phức tạp có thể gây lỗi riêng, ví dụ `ExceptionInInitializerError`.

### Bytecode không đồng nghĩa với lệnh CPU

Các instruction như `aload`, `invokevirtual`, `return` thuộc **tập lệnh JVM**. Chúng không phải instruction x86/ARM của CPU. JVM có thể diễn giải instruction hoặc biên dịch một số đoạn sang mã máy trong tiến trình. Vì vậy quy trình “Java → bytecode → JVM” giúp giải thích tính di động, còn hiệu năng thực tế phụ thuộc tối ưu runtime, thư viện, hệ điều hành và workload.

Tập quy tắc về class file, verifier, nạp lớp, liên kết và khởi tạo được định nghĩa bởi Java Virtual Machine Specification. Bài này phân biệt **hành vi quy định** với **cách triển khai thường gặp** (như HotSpot JIT).

## 7. Biên dịch thành công vẫn có thể lỗi khi chạy

Phân biệt lỗi theo pha giúp tìm nguyên nhân nhanh hơn:

| Hiện tượng | Thời điểm | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| `error: cannot find symbol` | Biên dịch | Sai tên, import, scope, hoặc thiếu classpath biên dịch | Kiểm tra khai báo/import và phụ thuộc |
| `incompatible types` | Biên dịch | Kiểu không tương thích với phép gán/lời gọi | Sửa kiểu dữ liệu hoặc cách chuyển đổi |
| `Could not find or load main class` | Khởi chạy | Sai tên đầy đủ hoặc classpath không trỏ đúng gốc package | Kiểm tra `-cp`, package, vị trí file |
| `NoClassDefFoundError` | Lúc nạp hoặc dùng lớp | Lớp đã tham chiếu không có định nghĩa phù hợp ở runtime, hoặc khởi tạo trước đó thất bại | Kiểm tra JAR, classpath/runtime và nguyên nhân gốc |
| `ClassNotFoundException` | Lúc runtime tải lớp theo API | Tên lớp được yêu cầu bằng API như `Class.forName` không tìm được | Kiểm tra tên, class loader, classpath/module path |
| `UnsupportedClassVersionError` | Lúc nạp lớp | Class file mới hơn runtime hỗ trợ | Nâng runtime hoặc biên dịch với `--release` phù hợp |
| `NoSuchMethodError` | Runtime linking | Class runtime không còn phương thức theo signature mà bytecode đã tham chiếu | Đồng bộ version thư viện và build lại |
| `NullPointerException`, `ArithmeticException` | Thực thi | Điều kiện/dữ liệu khi chạy không phù hợp | Kiểm tra logic, đầu vào, stack trace |

Các thông báo thực tế có thể có thêm chi tiết và khác nhau theo phiên bản. Chẳng hạn ứng dụng **có thể** biên dịch với phiên bản thư viện mới, nhưng lúc chạy lại dùng JAR cũ không còn method tương ứng; JVM chỉ phát hiện sự không tương thích khi tham chiếu liên quan được giải quyết. Đừng kết luận “`javac` đã pass nên runtime chắc chắn ổn”.

**Tệp class cũ là bẫy thường gặp.** Nếu vừa sửa code lỗi, `javac` thất bại nhưng trong thư mục `out` vẫn còn class file từ lần biên dịch trước, lệnh `java` có thể chạy mã cũ. Khi debug, đọc exit code của `javac` và thời điểm file class; dùng thư mục build sạch do công cụ build quản lý khi cần xác minh. Tránh xóa bừa dữ liệu không thuộc đầu ra build.

## 8. Ba cách chạy dễ bị nhầm

**Cách A — biên dịch rồi chạy lớp** (cách trọng tâm của bài):

```bash
javac -d out Hello.java
java -cp out Hello
```

Cách này để lại class file trong `out`, có thể quan sát bằng `javap`.

**Cách B — chạy trực tiếp một file nguồn với Java 11+**:

```bash
java Hello.java
```

Công cụ `java` hỗ trợ source-file mode: nó xử lý/biên dịch mã nguồn và chạy chương trình trong cùng một lệnh, thường không tạo `Hello.class` ra thư mục hiện tại như `javac`. Đây là tiện ích cho file đơn giản, **không chứng minh rằng Java bỏ qua bước biên dịch**. Lệnh này khác `java Hello`, vốn tìm lớp đã biên dịch trên classpath.

**Cách C — chạy một JAR có Main-Class**:

```bash
java -jar app.jar
```

Cách này yêu cầu JAR thích hợp có entry point (ví dụ manifest `Main-Class`). JAR là container có thể chứa nhiều class/resource; `-jar` không đơn thuần là cách viết khác của `-cp`. Chỉ đặt tên file là `app.jar` không khiến nó tự chạy được. Lệnh này minh họa cách khởi động, không giả định có sẵn file `app.jar` để chạy.

Trong dự án lớn, Maven/Gradle thường tự thiết lập `javac`, classpath, tài nguyên, test, packaging và lệnh chạy. Chúng **điều phối các bước**, không làm mất đi mô hình mã nguồn → class file → JVM.

## 9. Tự kiểm chứng trên môi trường của bạn

Đi theo từng bước để kiểm chứng đúng thứ gì được tạo, thứ gì được chạy:

1. Gõ `java -version` và `javac -version`; bảo đảm đang dùng JDK phù hợp (ưu tiên JDK 17+).
2. Biên dịch `Hello.java` bằng `javac -encoding UTF-8 -d out Hello.java`. Nếu lệnh báo lỗi, sửa lỗi trước khi chạy.
3. Kiểm tra file `out/Hello.class` thực sự tồn tại. Dùng `javap -classpath out -c Hello` để nhìn bytecode.
4. Chạy `java -cp out Hello` và đối chiếu stdout chính xác với ví dụ. Nếu không tìm thấy lớp, đối chiếu package và gốc classpath.
5. Thử thêm lỗi kiểu `int count = "5";` vào mã nguồn để thấy lỗi thuộc **compile time**. Hoàn tác lỗi, biên dịch lại.
6. Thử ví dụ `Lifecycle` để chứng kiến static initializer chạy trước `main`. Lưu ý output của ví dụ đến từ lần `java`, không phải `javac`.
7. Nếu có nhiều JDK, thử giải thích tại sao class file biên dịch bằng `--release 17` nhắm tới runtime Java 17, trong khi compile bằng release mới hơn có thể không chạy trên Java 17.

### Câu hỏi tự kiểm tra

- Vì sao `java -cp out com.example.app.Main` khác `java -cp out Main`?
- Tại sao một file `.java` có thể tạo nhiều file `.class`?
- Vì sao `javac` không báo được mọi `NullPointerException` có thể xảy ra khi chạy?
- `preparation` và `initialization` của lớp khác nhau ở điểm nào?
- Khi nào bạn nghi ngờ `UnsupportedClassVersionError`, khi nào nghi ngờ sai classpath?
- `java Hello.java` có thực sự loại bỏ việc biên dịch không?

Đáp án cốt lõi: `-cp` trỏ vào gốc tìm kiếm và tên lớp phải đúng package; các kiểu lồng nhau/phụ có thể thành class file riêng; nhiều lỗi phụ thuộc dữ liệu/runtime; preparation chuẩn bị giá trị mặc định cho static field còn initialization chạy initializer; class version khác classpath; source-file mode vẫn biên dịch trước khi thực thi.

## 10. Ghi nhớ

Trong Java, **`javac` biến mã nguồn thành các class file có bytecode**, còn **`java` khởi động môi trường chạy và JVM thực thi chương trình**. Class file không phải mã máy và không đảm bảo có đủ dependency hoặc runtime tương thích. Muốn chẩn đoán đúng, hãy quan sát riêng **mã nguồn → kết quả biên dịch → vị trí class file/classpath → hành vi khi chạy**, dùng `javac`, `java` và `javap` để xác minh từng bước.

Tài liệu tham chiếu chính thống: *The Java Language Specification* (quy tắc ngôn ngữ và compile-time), *The Java Virtual Machine Specification* (class file, loading, linking, initialization, execution) và tài liệu công cụ `javac`/`java`/`javap` của JDK đang sử dụng.