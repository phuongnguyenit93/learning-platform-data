# Quy tắc tên tệp với lớp public trong Java

## 1. Quy tắc cần nhớ

Với quy trình biên dịch tệp nguồn thông thường bằng **`javac`** (JDK 17+), một **lớp top-level được khai báo `public`** phải nằm trong tệp `.java` có **tên cơ sở trùng với tên lớp**, đúng cả chữ hoa/chữ thường.

~~~java
// Tệp Greeting.java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chao Java");
    }
}
~~~

Tên class là `Greeting`, do đó tên tệp phải là **`Greeting.java`**. Không đặt tên `Hello.java`, `greeting.java` hoặc `Greeting.class`.

Nếu lưu cùng mã vào `Hello.java` rồi chạy:

~~~bash
javac --release 17 Hello.java
~~~

Bạn sẽ gặp lỗi gần giống:

~~~text
Hello.java:2: error: class Greeting is public, should be declared in a file named Greeting.java
public class Greeting {
       ^
1 error
~~~

**Cách sửa:** đổi tên tệp thành `Greeting.java` **hoặc** đổi khai báo `public class Greeting` thành `public class Hello` và cập nhật các chỗ tham chiếu tên lớp.

Quy tắc này liên quan đến **tên tệp nguồn và khai báo top-level public type lúc biên dịch**. Nó khác với lỗi không tìm thấy class lúc chạy và không được sửa bằng cách đổi tên file `.class` thủ công.

## 2. Top-level, public và package-private

**Top-level class** là class khai báo trực tiếp trong đơn vị mã nguồn, không nằm bên trong một class hay interface khác.

~~~java
// Tệp Catalog.java
public class Catalog {   // top-level public class
}

class CatalogItem {       // top-level package-private class
}
~~~

Trong ví dụ này, `Catalog.java` hợp lệ vì có **một** top-level public class tên `Catalog`; class `CatalogItem` không `public`, nên không cần tệp riêng chỉ vì tên nó khác tên source.

| Trường hợp | Hợp lệ khi biên dịch bằng javac? | Lý do |
|---|---|---|
| `public class A` trong `A.java` | Có | Khớp tên |
| `public class A` trong `B.java` | Không | Tên top-level public class khác tên tệp |
| `class A` trong `B.java` | Có | Top-level class không public |
| `public class A` và `class B` trong `A.java` | Có | Chỉ `A` public |
| `public class A` và `public class B` trong `A.java` | Không | Hai top-level public type không thể cùng đáp ứng quy tắc đặt tên |

Bỏ `public` ở mức top-level tạo quyền truy cập **package-private**, tức là các mã phù hợp ở cùng package có thể tham chiếu. Điều đó không tự ngăn class có phương thức `main` hoặc tạo ra file bytecode.

Một class **lồng bên trong** class khác (*nested class*) không phải top-level class, nên không bị quy tắc “một tên tệp riêng” này áp đặt theo cách tương tự.

## 3. Biên dịch và chạy một public class đúng tên

Lưu đoạn ví dụ đầu trong `Greeting.java`, mở terminal tại thư mục chứa tệp. Kiểm tra JDK:

~~~bash
java -version
javac -version
~~~

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 Greeting.java
java -cp . Greeting
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\Greeting.java
java -cp . Greeting
~~~

Đầu ra:

~~~text
Xin chao Java
~~~

Sau khi biên dịch, thư mục thường có:

~~~text
Greeting.java
Greeting.class
~~~

- `javac` nhận **tên tệp nguồn** `Greeting.java`.
- `java` trong **class mode** nhận **tên lớp** `Greeting`, không phải `Greeting.java` hay `Greeting.class`.
- `-cp .` chỉ định thư mục hiện tại là classpath root.
- `--release 17` yêu cầu trình biên dịch tạo mã tương thích với Java 17 trong khả năng JDK đang dùng; cần compiler hỗ trợ release đó.

Hãy thử đặt nội dung `Greeting.java` vào `Welcome.java` nhưng giữ `public class Greeting`. Compiler sẽ từ chối. Nếu thay khai báo thành `public class Welcome`, bạn có thể dùng:

~~~bash
javac --release 17 Welcome.java
java -cp . Welcome
~~~

và nhận cùng dòng đầu ra. **Tên class và tên tệp phải được thay đồng bộ.**

## 4. Tệp không có public class: tên nguồn không nhất thiết là tên class chạy

Tạo tệp **`Examples.java`**:

~~~java
class Printer {
    static void show(String text) {
        System.out.println(text);
    }
}

class Runner {
    public static void main(String[] args) {
        Printer.show("Da chay Runner");
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 Examples.java
java -cp . Runner
~~~

Kết quả:

~~~text
Da chay Runner
~~~

Thông thường `javac` tạo ra **`Printer.class`** và **`Runner.class`**, dù source tên **`Examples.java`**. Không có class `Examples` được khai báo, nên `java Examples` không phải lệnh chạy đúng.

Kết luận từ ví dụ:

1. Một source có thể chứa nhiều top-level class không `public`.
2. Một source có thể tạo ra nhiều file `.class`.
3. Phương thức `main` có thể nằm trong class top-level không public; class ấy vẫn có thể được chọn để launch trong Java 17.
4. Dù quy tắc cho phép tên tệp khác tên class package-private, dự án thường dễ bảo trì hơn nếu tổ chức file theo tên class chính.

## 5. Không viết hai top-level public class trong cùng một tệp

Ví dụ **không hợp lệ** trong `Alpha.java`:

~~~java
public class Alpha {
}

public class Beta {
}
~~~

`javac Alpha.java` sẽ báo lỗi vì `public class Beta` yêu cầu tệp **`Beta.java`**.

Hướng sửa chuẩn là tách thành hai tệp:

**`Alpha.java`:**

~~~java
public class Alpha {
    public static void main(String[] args) {
        Beta.hello();
    }
}
~~~

**`Beta.java`:**

~~~java
public class Beta {
    public static void hello() {
        System.out.println("Hello from Beta");
    }
}
~~~

Từ thư mục chứa hai tệp:

~~~bash
javac --release 17 Alpha.java Beta.java
java -cp . Alpha
~~~

Đầu ra:

~~~text
Hello from Beta
~~~

Không phải class nào cũng cần `main`: `Alpha` làm điểm vào, `Beta` là class cộng tác. Quy tắc tên file vẫn áp dụng cho cả hai vì cả hai đều là **top-level public class**.

## 6. Có package thì tên tệp vẫn khớp tên class cơ sở

Tạo dự án:

~~~text
project/
└── src/
    └── demo/
        └── Launcher.java
~~~

**`src/demo/Launcher.java`:**

~~~java
package demo;

public class Launcher {
    public static void main(String[] args) {
        System.out.println("Package demo OK");
    }
}
~~~

Ở đây:

- Tên tệp nguồn: **`Launcher.java`**.
- Tên lớp đơn giản: **`Launcher`**.
- Tên lớp đầy đủ: **`demo.Launcher`**.
- `demo` là tên package; không đặt tên tệp là `demo.Launcher.java`.

Từ thư mục `project`:

**Bash:**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/demo/Launcher.java
java -cp out demo.Launcher
~~~

**PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out .\src\demo\Launcher.java
java -cp out demo.Launcher
~~~

Đầu ra:

~~~text
Package demo OK
~~~

Sau biên dịch, file bytecode nằm ở **`out/demo/Launcher.class`**. Lệnh chạy dùng `demo.Launcher`; classpath phải trỏ tới **`out`**, không phải `out/demo`.

Cấu trúc thư mục source phản ánh package là quy ước tốt và thuận tiện cho build tools. Nhưng **quy tắc tên cơ sở của file public class** vẫn là `Launcher.java`: package không được ghép thêm vào tên file.

## 7. Public nested class không cần file riêng

Tạo **`Outer.java`**:

~~~java
public class Outer {
    public static class Inner {
        public static String greeting() {
            return "Inner";
        }
    }

    public static void main(String[] args) {
        System.out.println(Inner.greeting());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 Outer.java
java -cp . Outer
~~~

Kết quả:

~~~text
Inner
~~~

`Outer` là top-level public class nên tệp có tên `Outer.java`. `Inner` là **nested public class** nên không cần tệp `Inner.java`. Compiler thường tạo các class file `Outer.class` và `Outer$Inner.class`.

Nếu đưa `public class Inner` ra **ngoài** thân của `Outer`, nó trở thành top-level class; khi ấy hai public class cần hai tệp riêng.

## 8. Quy tắc cũng áp dụng cho các top-level public type khác

Với Java 17, không chỉ `class` mới bị yêu cầu khớp tên:

| Khai báo top-level | Tên tệp |
|---|---|
| `public class Account` | `Account.java` |
| `public interface Payment` | `Payment.java` |
| `public enum Status` | `Status.java` |
| `public record Point(int x, int y)` | `Point.java` |
| `public @interface Tracked` | `Tracked.java` |

Ví dụ **`Point.java`**:

~~~java
public record Point(int x, int y) {
}
~~~

Chạy `javac --release 17 Point.java` để biên dịch. Nếu giữ nguyên `public record Point` mà đổi tên source thành `Coordinate.java`, lỗi đặt tên sẽ xuất hiện.

Không suy ra mọi interface, enum hay record phải là `public`. Một top-level type thiếu modifier `public` có thể dùng quyền truy cập package-private như ví dụ class thông thường.

## 9. Phân biệt lỗi compile và lỗi launch

| Triệu chứng | Giai đoạn | Điều cần sửa |
|---|---|---|
| `class X is public, should be declared in a file named X.java` | `javac` | Đổi tên source hoặc tên top-level public type |
| Có hai top-level public type trong một source | `javac` | Tách thành hai source files |
| `Could not find or load main class` | `java` tìm class | Kiểm tra tên đầy đủ, classpath root và file bytecode |
| `Main method not found` | `java` tìm entry point | Bổ sung main hợp lệ vào class định chạy |
| Chạy ra phiên bản kết quả cũ sau khi sửa source | Runtime | Lưu source, biên dịch lại và kiểm tra đúng classpath |
| `UnsupportedClassVersionError` | JVM nạp bytecode | Kiểm tra runtime và mức release build; không phải lỗi đặt tên source |

**Ghi nhớ:** lỗi đặt tên tệp xảy ra **trước khi chạy**, trong bước biên dịch của `javac`. Đổi classpath hoặc thêm `-cp` không giải quyết lỗi này.

Ngược lại, class public có tên đúng, compile tốt vẫn có thể không launch được nếu package/classpath sai hoặc không có `main`.

## 10. Các trường hợp dễ nhầm

**Chữ hoa/chữ thường.** `public class Order` yêu cầu `Order.java`. Trên các hệ thống phân biệt hoa/thường, `order.java` có thể là file khác. Luôn dùng đúng ký tự để tránh lỗi khi chuyển dự án sang Linux.

**Tên file và tên package là hai phần riêng.** `public class App` trong `package demo;` vẫn ở `App.java`; khi chạy class mode dùng tên `demo.App`.

**Class có main nhưng không public.** Điều này không buộc source file phải mang tên class. Ví dụ `Runner` trong `Examples.java` vẫn được chạy nếu có `main` phù hợp và classpath đúng.

**Public class không có main.** Biên dịch vẫn hợp lệ; một class làm thư viện không nhất thiết có entry point riêng.

**Một source có nhiều bytecode file.** Top-level khác nhau hoặc nested class đều có thể khiến `javac` tạo nhiều `.class`. Đừng tự đổi tên output bytecode để sửa lỗi tên public class.

**`java File.java` khác `java ClassName`.** Java 11+ hỗ trợ source-file launching với quy tắc riêng. Trong bài này, để kiểm chứng tên file của top-level public type, hãy dùng `javac File.java` trước, sau đó `java ClassName`. Đừng lấy hành vi của source-file mode làm bằng chứng phủ định quy tắc biên dịch tệp nguồn bằng `javac`.

## 11. Bài tập có đáp án

### Bài A — chọn tên tệp

~~~java
public class PaymentService {
}
~~~

**Đáp án:** đặt trong `PaymentService.java`, đúng hoa/thường. Không dùng `paymentservice.java`.

### Bài B — một public và một package-private class

Tệp **`Demo.java`**:

~~~java
class Helper {
    static int twice(int x) { return x * 2; }
}

public class Demo {
    public static void main(String[] args) {
        System.out.println(Helper.twice(6));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 Demo.java
java -cp . Demo
~~~

**Đáp án:** hợp lệ; in **`12`**. `Demo` là top-level public class khớp tên tệp, `Helper` không public nên được giữ chung file.

### Bài C — phân biệt hai vấn đề

Tệp **`Hello.java`** chứa:

~~~java
package demo;
public class Welcome {
    public static void main(String[] args) {
        System.out.println("Hi");
    }
}
~~~

**Đáp án:** `javac Hello.java` báo lỗi đặt tên vì phải là **`Welcome.java`**. Sau khi sửa tên nguồn, compile với `-d out`, lệnh chạy cần dùng **`java -cp out demo.Welcome`** vì class thuộc package `demo`.

### Bài D — hai top-level public class

Tệp `A.java` có cả `public class A` và `public class B`. Hãy nêu cách sửa.

**Đáp án:** tách ra `A.java` và `B.java`, mỗi file giữ public class tương ứng. Nếu `B` chỉ cần sử dụng nội bộ package và thiết kế cho phép, một lựa chọn khác là bỏ `public` khỏi `B`; không tự đổi API public khi còn mã phụ thuộc.

### Bài E — nested class

Có `public class Outer` chứa `public static class Inner`. Có cần tạo `Inner.java` không?

**Đáp án:** **không**. `Inner` không phải top-level type; `Outer.java` là tệp cần khớp tên của `Outer`.

## 12. Checklist ghi nhớ

- [ ] Giải thích được `public class X` ở top-level cần tệp `X.java`.
- [ ] Phân biệt top-level class, package-private class và nested public class.
- [ ] Biết khi nào có thể có nhiều class trong một tệp, khi nào phải tách.
- [ ] Không nhầm tên tệp `.java` với tên class dùng ở lệnh `java`.
- [ ] Chạy được ví dụ `Greeting.java` và `demo.Launcher` trên JDK 17+.
- [ ] Nắm quy tắc với top-level `public interface`, `public enum`, `public record`, `public @interface`.
- [ ] Biết đọc lỗi `should be declared in a file named...` và sửa đúng nguyên nhân.
- [ ] Phân biệt lỗi tên source khi compile với lỗi classpath/main lúc chạy.

**Kết luận:** Quy tắc trung tâm khi biên dịch bằng `javac` là **tên tệp nguồn `.java` phải khớp tên top-level type `public` khai báo bên trong**. Những class top-level không public và class lồng nhau không phải áp dụng theo cách này. Khi chạy class đã biên dịch, `java` nhận tên class (kèm package nếu có), nên cần phân biệt tên source, tên class và vị trí bytecode.