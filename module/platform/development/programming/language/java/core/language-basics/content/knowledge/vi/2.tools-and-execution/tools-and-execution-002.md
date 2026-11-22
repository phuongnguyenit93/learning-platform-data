# Tạo tệp nguồn và biên dịch bằng javac

Để máy tính thực thi chương trình Java, trước tiên bạn cần viết **mã nguồn** vào tệp có đuôi `.java`, rồi sử dụng **trình biên dịch `javac`** của JDK để tạo **bytecode** trong tệp `.class`. Sau đó, lệnh `java` khởi động JVM để chạy lớp có phương thức `main`.

Bài này hướng dẫn thao tác từ đầu bằng **JDK 17 trở lên**, sử dụng terminal Windows PowerShell hoặc Linux. Không cần IDE, Maven, Gradle hay thư viện ngoài.

## 1. Phân biệt ba thứ rất dễ nhầm

| Thành phần | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| Tệp nguồn `.java` | Chứa mã mà người lập trình viết | `HelloCompiler.java` |
| Lệnh `javac` | Phân tích mã, kiểm tra nhiều lỗi và tạo bytecode | `javac HelloCompiler.java` |
| Tệp `.class` | Kết quả biên dịch cho JVM | `HelloCompiler.class` |
| Lệnh `java` | Chạy lớp qua JVM; với ví dụ này gọi `main` | `java HelloCompiler` |
| JDK | Bộ công cụ phát triển, gồm `javac` và các công cụ chạy Java | JDK 17+ |

**`javac` không chạy chương trình.** Một lần biên dịch thành công cũng không chứng minh thuật toán đúng với mọi dữ liệu. Nó chủ yếu xác nhận mã thỏa những quy tắc cú pháp, kiểu và ngữ nghĩa mà compiler có thể kiểm tra.

Quy trình tổng quát:

~~~text
Mã nguồn HelloCompiler.java
         |
         | javac -encoding UTF-8 -d out src/HelloCompiler.java
         v
Bytecode out/HelloCompiler.class
         |
         | java -cp out HelloCompiler
         v
JVM thực thi -> Kết quả trong terminal
~~~

## 2. Kiểm tra JDK trước khi viết mã

Mở **PowerShell** trên Windows hoặc **terminal** trên Linux, chạy:

~~~bash
java -version
javac -version
~~~

Ví dụ kết quả cho JDK 17 có thể có dạng:

~~~text
openjdk version "17.0.x" ...
javac 17.0.x
~~~

Phần `x` đại diện số bản vá; kết quả thật thay đổi theo bản phân phối JDK. Điều cần xác nhận là cả **`java` và `javac` cùng có thể được gọi** và phiên bản đáp ứng yêu cầu.

Nếu thấy thông báo `javac` không được nhận diện:

- Kiểm tra đã cài **JDK**, thay vì chỉ có runtime Java.
- Kiểm tra biến môi trường `PATH` có thư mục `bin` của JDK phù hợp.
- Mở terminal mới sau khi thay đổi cấu hình môi trường.
- Kiểm tra xem `java` và `javac` có đang trỏ tới hai JDK khác nhau hay không.

Trên Windows PowerShell, có thể xem đường dẫn lệnh bằng `Get-Command java, javac`; trên Linux, dùng `command -v java` và `command -v javac`. Đây là các lệnh kiểm tra môi trường, không phải lệnh biên dịch.

## 3. Tạo thư mục dự án đơn giản

Chọn một thư mục làm nơi thực hành, ví dụ `java-compile-demo`, rồi mở terminal **ngay trong thư mục này**. Cấu trúc mong muốn:

~~~text
java-compile-demo/
├── src/
│   └── HelloCompiler.java
└── out/                 (chứa .class sau khi biên dịch)
~~~

Tạo thư mục:

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path src, out | Out-Null
~~~

**Linux (Bash):**

~~~bash
mkdir -p src out
~~~

Dùng trình soạn thảo văn bản để tạo tệp **`src/HelloCompiler.java`**. Lưu dưới dạng **UTF-8**, chọn đúng phần mở rộng `.java`; tránh vô tình lưu thành `HelloCompiler.java.txt` trên Windows.

## 4. Viết chương trình Java đầu tiên

Nội dung đầy đủ của `src/HelloCompiler.java`:

~~~java
public class HelloCompiler {
    public static void main(String[] args) {
        String visitor = args.length > 0 ? args[0] : "ban";
        System.out.println("Xin chao, " + visitor + "!");
    }
}
~~~

Những thành phần cần hiểu:

- `public class HelloCompiler` khai báo lớp công khai. Tệp chứa lớp công khai này phải mang tên `HelloCompiler.java` (đúng chữ hoa/chữ thường).
- Dấu `{ }` đánh dấu khối lớp và khối phương thức.
- `public static void main(String[] args)` là điểm bắt đầu khi chạy chương trình Java theo cách trong bài này.
- `args` là mảng các đối số mà bạn truyền sau tên lớp khi chạy.
- Toán tử ba ngôi `?:` chọn đối số đầu tiên nếu có; nếu không có thì dùng chuỗi mặc định `"ban"`.
- `System.out.println(...)` in một dòng ra terminal.
- Dấu `;` kết thúc các câu lệnh Java tương ứng.

Không cần viết `package` cho ví dụ đầu này: lớp nằm trong **unnamed package** để lệnh biên dịch và chạy đơn giản.

## 5. Biên dịch từ mã nguồn thành bytecode

Từ thư mục `java-compile-demo`, chạy **cùng một lệnh** trên PowerShell hoặc Bash:

~~~bash
javac -encoding UTF-8 -d out src/HelloCompiler.java
~~~

Ý nghĩa các tham số:

| Thành phần | Ý nghĩa |
| --- | --- |
| `javac` | Gọi trình biên dịch Java |
| `-encoding UTF-8` | Chỉ định cách đọc ký tự mã nguồn |
| `-d out` | Đặt thư mục gốc chứa các tệp `.class` được tạo |
| `src/HelloCompiler.java` | Đường dẫn của tệp nguồn cần biên dịch |

Nếu thành công, `javac` thường **không in thông báo**. Hãy kiểm tra thư mục `out`: bạn sẽ thấy `HelloCompiler.class`.

Lưu ý: vì lệnh đã chỉ định `-d out`, thư mục `out` phải tồn tại trước khi chạy. Đối với mã **không có package**, file đầu ra nằm ngay trong `out`. Không cần di chuyển file `.class` bằng tay.

### Chạy kết quả biên dịch

~~~bash
java -cp out HelloCompiler
~~~

Kết quả:

~~~text
Xin chao, ban!
~~~

Thử truyền tên:

~~~bash
java -cp out HelloCompiler Minh
~~~

Kết quả:

~~~text
Xin chao, Minh!
~~~

Giải thích:

- `-cp out` (viết đầy đủ là `-classpath out`) chỉ nơi JVM cần tìm lớp của chương trình.
- `HelloCompiler` là **tên lớp**, không phải tên file `HelloCompiler.java` hoặc `HelloCompiler.class`.
- `Minh` là đối số dòng lệnh, xuất hiện ở `args[0]`.

Dùng dấu `/` trong các đường dẫn ở ví dụ trên phù hợp cho những lệnh Java này trên cả Windows và Linux. Nếu đường dẫn thực tế chứa khoảng trắng, đặt **toàn bộ đường dẫn** trong dấu nháy kép.

## 6. Sửa mã, biên dịch lại rồi chạy lại

Thử thay dòng:

~~~java
System.out.println("Xin chao, " + visitor + "!");
~~~

thành:

~~~java
System.out.println("Chuc ban hoc Java tot, " + visitor + "!");
~~~

Sau khi **lưu tệp nguồn**, chạy lại:

~~~bash
javac -encoding UTF-8 -d out src/HelloCompiler.java
java -cp out HelloCompiler Minh
~~~

Kết quả mới:

~~~text
Chuc ban hoc Java tot, Minh!
~~~

Chỉ sửa `.java` rồi chạy lại `java` mà **không biên dịch lại** có thể khiến bạn nhìn thấy **bytecode cũ** trong `.class`. Đặc biệt nếu lần biên dịch mới thất bại nhưng file `.class` cũ vẫn còn, JVM vẫn có thể chạy lớp cũ. Vì vậy, khi thử sửa mã, hãy đọc kết quả biên dịch trước khi tin rằng bản mới đã được chạy.

## 7. Khi chương trình có `package`

Từ khóa `package` xác định namespace của lớp. Ví dụ khác này độc lập với `HelloCompiler`.

Tạo thư mục `src/tutorial`:

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path src/tutorial | Out-Null
~~~

**Linux:**

~~~bash
mkdir -p src/tutorial
~~~

Lưu mã sau vào **`src/tutorial/PackageHello.java`**:

~~~java
package tutorial;

public class PackageHello {
    public static void main(String[] args) {
        System.out.println("Package works");
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 -d out src/tutorial/PackageHello.java
~~~

Vì lớp khai báo `package tutorial;`, compiler tạo file:

~~~text
out/
└── tutorial/
    └── PackageHello.class
~~~

Chạy với **tên lớp đầy đủ kèm package**:

~~~bash
java -cp out tutorial.PackageHello
~~~

Kết quả:

~~~text
Package works
~~~

Không chạy bằng `java -cp out PackageHello` vì lớp này không thuộc unnamed package. Khi dùng `-d out`, `javac` sắp xếp output theo package; `java` cần tìm lớp bằng tên đủ điều kiện.

**Phân biệt:** folder `src/tutorial` là vị trí tổ chức tệp nguồn theo thói quen tốt; khai báo `package tutorial;` trong nội dung mã mới xác định package Java. Trong một dự án nhỏ, hãy để cấu trúc thư mục phản ánh package cho dễ hiểu và dễ xây dựng.

## 8. Một số lỗi biên dịch thường gặp

Bạn có thể thử từng lỗi sau, **mỗi lần chỉ sửa một chỗ** rồi biên dịch lại.

| Tình huống | Triệu chứng thường gặp | Cách xử lý |
| --- | --- | --- |
| Lưu file thành `HelloCompiler.java.txt` | Không tìm thấy tệp `.java` | Hiển thị phần mở rộng và đổi đúng tên |
| Viết `public class HelloCompilor` trong `HelloCompiler.java` | Lỗi tên lớp công khai không khớp file | Đổi tên lớp hoặc file cho đúng |
| Thiếu `;` hoặc `}` | `';' expected` hoặc lỗi cú pháp | Kiểm tra câu lệnh và dấu ngoặc |
| Gán `int count = "3";` | `incompatible types` | Sửa kiểu hoặc chuyển chuỗi đúng cách |
| Gọi `javac` ở sai thư mục | `file not found` | Kiểm tra thư mục làm việc và đường dẫn nguồn |
| Chạy `java HelloCompiler.class` | Không tìm thấy lớp phù hợp | Dùng tên lớp `HelloCompiler`, bỏ đuôi file |
| Quên `-cp out` khi đã dùng `-d out` | JVM không tìm thấy lớp | Thêm `-cp out` |
| Có `package tutorial;` nhưng chạy tên ngắn | Không tìm thấy main class | Chạy `tutorial.PackageHello` |
| `java` cũ hơn phiên bản dùng để biên dịch | `UnsupportedClassVersionError` khi chạy | Dùng runtime tương thích hoặc biên dịch cho phiên bản đích |

Các thông báo có thể khác theo bản JDK và hệ điều hành. Điều quan trọng là **phân loại nguyên nhân**: tên lớp, thư mục, cú pháp, kiểu dữ liệu, package hay phiên bản.

### Tự thử một lỗi compiler có chủ đích

Trong file `HelloCompiler.java`, thêm dòng sau **bên trong `main`**:

~~~java
int hours = "two"; // Sai: String không thể gán cho int.
~~~

Chạy `javac -encoding UTF-8 -d out src/HelloCompiler.java`, bạn sẽ nhận lỗi kiểu dữ liệu. Sửa thành:

~~~java
int hours = 2;
~~~

Sau đó biên dịch lại. Đây là minh họa rằng `javac` có thể từ chối mã **trước khi chương trình chạy**.

## 9. Các tùy chọn `javac` hữu ích sau khi đã chạy được cơ bản

| Lệnh hoặc tùy chọn | Khi nào hữu ích? |
| --- | --- |
| `javac -version` | Xác minh phiên bản compiler |
| `javac -encoding UTF-8 ...` | Ấn định encoding đầu vào nguồn |
| `javac -d out ...` | Tách tệp `.class` khỏi thư mục nguồn |
| `javac -Xlint:all ...` | Hiển thị thêm cảnh báo compiler (tùy mã) |
| `javac --release 17 ...` | Khi dùng JDK mới hơn để hướng tới API/ngôn ngữ Java 17 |
| `javac -cp libs/something.jar ...` | Khi thực sự cần biên dịch với thư viện ngoài; đường dẫn chỉ là ví dụ |

Ví dụ biên dịch nhắm Java 17 khi đang sử dụng JDK hỗ trợ tùy chọn này:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/HelloCompiler.java
~~~

`--release 17` ràng buộc mức ngôn ngữ và API nền tảng Java tương ứng với release được hỗ trợ. Tuy vậy, nó không tự bảo đảm rằng **mọi thư viện bên thứ ba** hoặc cấu hình runtime của bạn đều tương thích; phải kiểm tra riêng các phụ thuộc.

Không cần thêm các tham số phức tạp khi bài toán chỉ có một tệp nguồn.

## 10. Bài tập tự thực hành

**Bài 1 — Biên dịch không có IDE.** Tạo một thư mục mới, lưu `src/HelloCompiler.java` đúng tên, rồi chạy `javac` và `java`. Ghi lại tên file `.class` được tạo. Giải thích vì sao bước chạy không dùng `.java` làm đối số lớp.

**Bài 2 — Truyền tham số.** Chạy `java -cp out HelloCompiler Lan`. Dự đoán chính xác một dòng kết quả trước khi chạy. Thử bỏ tham số và giải thích nhánh `args.length > 0`.

**Bài 3 — Tìm lỗi.** Đổi tên lớp thành `HelloCompilor` nhưng giữ nguyên tên tệp. Dự đoán `javac` báo lỗi ở bước nào và sửa tối thiểu ra sao. Sau bài tập, khôi phục tên đúng.

**Bài 4 — Package.** Biên dịch `src/tutorial/PackageHello.java` và giải thích vì sao output nằm trong `out/tutorial/`. So sánh `java -cp out PackageHello` với `java -cp out tutorial.PackageHello`.

**Bài 5 — Chạy sau khi sửa nguồn.** Đổi câu in ra terminal, chạy chương trình nhưng cố ý bỏ bước `javac`. Mô tả vì sao kết quả có thể vẫn là câu cũ. Sau đó biên dịch lại và đối chiếu.

### Checklist trước khi chuyển sang bài Java tiếp theo

- [ ] Cài JDK và gọi được cả `java` lẫn `javac`.
- [ ] Tạo được file nguồn `.java` bằng UTF-8.
- [ ] Hiểu quan hệ giữa tên file và tên lớp `public`.
- [ ] Biên dịch với `javac -encoding UTF-8 -d out ...`.
- [ ] Chạy bằng `java -cp out TenLop`.
- [ ] Giải thích đúng `package` và tên lớp đầy đủ khi có package.
- [ ] Phân biệt lỗi biên dịch, lỗi lúc chạy và chương trình chạy bản `.class` cũ.
- [ ] Tự sửa ít nhất một lỗi `javac` rồi biên dịch và chạy lại thành công.

## Ghi nhớ

**`.java` là mã nguồn, `javac` biên dịch mã nguồn thành `.class`, còn `java` khởi động JVM để chạy lớp đã biên dịch.** Khi quen quy trình **tạo tệp → biên dịch → sửa lỗi → chạy → đối chiếu kết quả**, bạn có thể học cú pháp Java mà không phụ thuộc vào nút Run của IDE.
