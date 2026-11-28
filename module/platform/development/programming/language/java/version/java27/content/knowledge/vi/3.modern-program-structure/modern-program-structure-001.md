# Cấu trúc chương trình Java và các dạng phương thức `main` được JDK hỗ trợ

Trong Java, mã nguồn thường được tổ chức thành các file `.java`, mỗi file chứa khai báo package, import và một hoặc nhiều kiểu dữ liệu cấp cao nhất như class, interface, enum hoặc record. Khi khởi chạy một ứng dụng bằng lệnh `java`, JDK tìm một phương thức `main` phù hợp trong lớp hoặc interface được chỉ định rồi gọi phương thức đó để bắt đầu thực thi.

Với JDK 27, `public static void main(String[] args)` vẫn là dạng quen thuộc và có tính tương thích rộng. Tuy nhiên, từ Java 25, quy tắc khởi chạy đã hỗ trợ thêm phương thức `main` không có tham số, phương thức `main` dạng instance và compact source file. Những khả năng này đã là tính năng ngôn ngữ chính thức trong JDK 27, không cần bật preview.

## 1. Cấu trúc cơ bản của một file Java

Một compilation unit thông thường có thể gồm ba phần theo thứ tự:

1. Khai báo package, nếu file thuộc một package có tên.
2. Các khai báo import để sử dụng kiểu hoặc thành viên từ package khác.
3. Một hoặc nhiều khai báo kiểu cấp cao nhất, chẳng hạn class, interface, enum hoặc record.

Ví dụ:

```java
package com.example;

import java.util.Arrays;

public class HelloApp {
    private final String greeting;

    public HelloApp(String greeting) {
        this.greeting = greeting;
    }

    public void run(String[] args) {
        System.out.println(greeting);
        System.out.println("Arguments: " + Arrays.toString(args));
    }

    public static void main(String[] args) {
        HelloApp app = new HelloApp("Hello, Java 27!");
        app.run(args);
    }
}
```

Trong ví dụ này:

- `package com.example;` đặt lớp vào package `com.example`. Nếu không khai báo package, lớp thuộc unnamed package.
- `import java.util.Arrays;` cho phép dùng tên ngắn `Arrays` thay vì tên đầy đủ.
- `public class HelloApp` khai báo một lớp cấp cao nhất.
- `greeting` là field lưu trạng thái của đối tượng.
- `HelloApp(String greeting)` là constructor khởi tạo đối tượng.
- `run(String[] args)` là phương thức instance chứa phần xử lý của ứng dụng.
- `main(String[] args)` là điểm vào mà Java launcher có thể gọi.

Với cách biên dịch thông thường bằng `javac`, file chứa lớp public cấp cao nhất thường được đặt cùng tên lớp, ví dụ `HelloApp.java`. Khai báo package phải đứng trước các khai báo import; import phải đứng trước khai báo kiểu.

### Các thành phần bên trong một kiểu

Một class Java có thể chứa:

| Thành phần | Vai trò |
|---|---|
| Field | Lưu trạng thái của đối tượng hoặc của class |
| Constructor | Tạo và khởi tạo đối tượng |
| Method | Định nghĩa hành vi hoặc thao tác |
| Initializer | Thực hiện logic khởi tạo static hoặc instance theo thời điểm khởi tạo tương ứng |
| Nested class/interface/enum/record | Tổ chức các kiểu chỉ có ý nghĩa trong phạm vi kiểu bao ngoài |

Không phải class nào cũng cần tất cả các thành phần này. Một class tiện ích có thể chỉ chứa các field hằng và phương thức static; một class mô hình thường có field, constructor và phương thức instance.

## 2. Vai trò của phương thức `main`

`main` là tên phương thức mà Java launcher nhận diện theo quy tắc khởi chạy của Java. Đây không phải từ khóa của ngôn ngữ. Một phương thức có tên `main` chỉ trở thành điểm vào hợp lệ khi chữ ký và quyền truy cập của nó đáp ứng quy tắc trong Java Language Specification (JLS), mục 12.1.4.

Trong JDK 27, một candidate `main` method phải đáp ứng các điều kiện sau:

- Tên phương thức là `main`.
- Kiểu trả về là `void`.
- Phương thức có một tham số kiểu `String[]`, hoặc không có tham số.
- Phương thức có quyền truy cập `public`, `protected` hoặc package-private (không ghi modifier truy cập).
- Phương thức có thể là `static` hoặc instance method.
- Có thể khai báo thêm mệnh đề `throws` nếu cần.

Phương thức `private` không phải candidate `main` method. Kiểu tham số `String...` tương đương `String[]`; đây là hai cách viết của cùng một kiểu tham số, không phải hai dạng chữ ký khác nhau.
JLS xét cả phương thức được khai báo trực tiếp trong kiểu khởi chạy lẫn phương thức được kế thừa, miễn là phương thức đáp ứng các điều kiện trên.

Có thể nhìn các lựa chọn theo ba trục:

| Trục | Các lựa chọn hợp lệ |
|---|---|
| Quyền truy cập | `public`, `protected`, package-private |
| Loại phương thức | `static`, instance |
| Tham số | Một `String[]`, hoặc không có tham số |

Ba lựa chọn quyền truy cập, hai lựa chọn loại phương thức và hai lựa chọn tham số tạo thành 12 dạng kết hợp. Dạng `String...` là cách viết varargs tương đương với `String[]`.

### 2.1. Dạng static có mảng tham số

Dạng truyền thống vẫn được hỗ trợ đầy đủ:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java 27!");
    }
}
```

Có thể viết tham số bằng varargs:

```java
public class VarargsMain {
    public static void main(String... args) {
        System.out.println("Number of arguments: " + args.length);
    }
}
```

Trong cả hai trường hợp, bên trong phương thức, `args` có kiểu `String[]`. Mỗi đối số truyền từ dòng lệnh trở thành một phần tử của mảng.

### 2.2. Dạng static không có tham số

Nếu chương trình không cần nhận đối số dòng lệnh, phương thức có thể không khai báo tham số:

```java
class Main {
    static void main() {
        System.out.println("Application started");
    }
}
```

Phương thức vẫn phải trả về `void`. Vì không có tham số, chương trình không nhận mảng đối số dòng lệnh thông qua phương thức này.

### 2.3. Dạng instance có tham số

Phương thức `main` không bắt buộc phải là static:

```java
class Main {
    void main(String[] args) {
        String name = args.length == 0 ? "developer" : args[0];
        System.out.println("Hello, " + name);
    }
}
```

Khi launcher chọn một instance `main` method, nó tạo một đối tượng của lớp bằng constructor không tham số trước, sau đó gọi phương thức trên đối tượng đó. Vì vậy, lớp cần có constructor không tham số có thể truy cập được. Nếu đã tự khai báo constructor có tham số và không còn constructor mặc định, hãy bổ sung constructor không tham số phù hợp khi muốn khởi chạy bằng instance `main`.

### 2.4. Dạng instance không có tham số

Đây là dạng ngắn gọn nhất khi dùng một class tường minh:

```java
class Main {
    void main() {
        System.out.println("Hello from an instance main method");
    }
}
```

Launcher tạo đối tượng rồi gọi `main()`. Điều này cho phép phương thức truy cập trực tiếp field và các phương thức instance khác của đối tượng.

### 2.5. Launcher chọn phương thức nào?

Nếu lớp có cả candidate `main(String[] args)` và candidate `main()`, launcher ưu tiên dạng có tham số `String[]`. Quy tắc này áp dụng trước khi xét phương thức được chọn là static hay instance:

1. Tìm candidate `main` có một tham số `String[]`.
2. Nếu tìm được, gọi phương thức đó và truyền mảng đối số dòng lệnh.
3. Nếu không có, tìm candidate `main` không tham số và gọi nó.
4. Nếu phương thức được chọn là instance method, launcher tạo đối tượng bằng constructor không tham số rồi mới gọi phương thức.

Ví dụ sau có hai overload:

```java
class Main {
    static void main(String[] args) {
        System.out.println("main(String[]) was selected");
    }

    void main() {
        System.out.println("main() was selected");
    }
}
```

Khi chạy lớp này, launcher chọn `main(String[] args)`. Việc phương thức có tham số được ưu tiên không phụ thuộc vào việc nó là static hay instance.

## 3. Nhận đối số từ dòng lệnh

Khi dùng dạng `main(String[] args)`, launcher truyền các đối số đứng sau tên lớp hoặc tên file nguồn vào mảng `args`.

Ví dụ:

```java
public class ArgumentDemo {
    public static void main(String[] args) {
        for (int i = 0; i < args.length; i++) {
            System.out.println(i + ": " + args[i]);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ArgumentDemo.java
java ArgumentDemo dev 27
```

Kết quả:

```text
0: dev
1: 27
```

Tên chương trình hoặc tên lớp không nằm trong `args`. Nếu không truyền đối số, `args` là mảng rỗng. Nếu dùng `main()` không tham số, phương thức đó không nhận các đối số dòng lệnh.

## 4. Compact source file trong Java 27

JEP 512 — Compact Source Files and Instance Main Methods — đã trở thành tính năng chính thức từ Java 25. Vì vậy, JDK 27 hỗ trợ cách viết chương trình đơn file mà không cần khai báo class tường minh.

Ví dụ, file `HelloWorld.java` có thể chỉ chứa:

```java
void main() {
    IO.println("Hello, Java 27!");
}
```

Đây là một compact source file. Compiler hiểu các khai báo cấp cao nhất như field và method trong file là thành viên của một class được khai báo ngầm. Class này:

- Là class cấp cao nhất, `final`, thuộc unnamed package.
- Kế thừa `java.lang.Object` và không triển khai interface nào.
- Có constructor mặc định không tham số.
- Chứa các field, method và kiểu thành viên được khai báo trong file.
- Phải có ít nhất một candidate `main` method có thể khởi chạy.

Do class được khai báo ngầm không thể được tham chiếu bằng tên trong mã nguồn, compact source file phù hợp với chương trình độc lập hoặc ví dụ học tập. Khi chương trình cần trở thành một API có kiểu được class khác tham chiếu, hãy chuyển sang class tường minh.

Compact source file không khai báo package có tên. Các khai báo import vẫn có thể đặt ở đầu file. Ngoài các kiểu được import ngầm từ `java.lang`, compact source file còn tự động import theo nhu cầu các public top-level class và interface thuộc những package được module `java.base` export.

### 4.1. Console I/O trong compact source file

JDK cung cấp class `java.lang.IO` với các phương thức cơ bản như `IO.print(...)`, `IO.println(...)` và `IO.readln(...)`. Vì class `IO` nằm trong `java.lang`, có thể gọi bằng tên `IO` mà không cần import.

Hãy gọi phương thức kèm tên class, ví dụ `IO.println(...)`. Các phương thức static của `IO` không được tự động static-import vào compact source file.

Ví dụ đọc một dòng:

```java
void main() {
    String name = IO.readln("Your name: ");
    IO.println("Hello, " + name + "!");
}
```

Có thể khai báo field và method hỗ trợ ở cấp cao nhất của file:

```java
String greeting = "Hello, Java 27!";

String createMessage(String name) {
    return greeting + " Welcome, " + name + ".";
}

void main(String[] args) {
    String name = args.length == 0 ? "developer" : args[0];
    IO.println(createMessage(name));
}
```

Các khai báo trên được hiểu là thành viên của class ngầm định. Vì `main` là instance method, nó có thể sử dụng field `greeting` và gọi trực tiếp `createMessage(...)`.

### 4.2. Chạy compact source file

Có thể chạy trực tiếp file nguồn bằng Java launcher:

```bash
java HelloWorld.java
```

Cách này dùng source-file mode: launcher biên dịch file nguồn và thực thi chương trình mà không yêu cầu người dùng gọi `javac` trước.

Cũng có thể biên dịch tường minh rồi chạy class đã biên dịch:

```bash
javac HelloWorld.java
java HelloWorld
```

Tên class do compiler tạo cho compact source file là chi tiết triển khai dựa trên file nguồn. Không thể dùng tên class ngầm định đó để tham chiếu class từ mã nguồn khác.

## 5. Chọn dạng chương trình phù hợp

| Nhu cầu | Cách viết phù hợp |
|---|---|
| Ứng dụng cần tương thích với nhiều phiên bản JDK | Class tường minh với `public static void main(String[] args)` |
| Ứng dụng cần nhận tham số dòng lệnh | Candidate `main(String[] args)` hoặc `main(String... args)` |
| Chương trình cần dùng trạng thái instance ngay tại điểm vào | Instance `main` trong class tường minh |
| Ví dụ nhỏ hoặc chương trình độc lập một file trên JDK 25+ | Compact source file với `void main()` hoặc `void main(String[] args)` |
| Chương trình cần được class khác tham chiếu như một API | Class, interface, record hoặc enum được khai báo tường minh trong package có tên |

Dạng `public static void main(String[] args)` vẫn là lựa chọn thực tế khi cần chạy trên nhiều thế hệ JDK hoặc khi dự án, công cụ build và môi trường triển khai đã quy ước điểm vào theo cách này. Các dạng mới trong Java 25+ giúp viết chương trình nhỏ gọn hơn và cho phép điểm vào sử dụng trạng thái instance. Hãy chọn theo phiên bản JDK mục tiêu và cấu trúc ứng dụng.

## 6. Những lỗi thường gặp

- **Sai kiểu trả về:** `int main(...)` hoặc `String main(...)` không phải candidate; kiểu trả về phải là `void`.
- **Sai kiểu tham số:** `main(String arg)` không hợp lệ; tham số phải là một mảng `String[]` (hoặc cách viết varargs `String...`) hoặc không có tham số.
- **Dùng private:** `private` không thuộc các mức truy cập được launcher chấp nhận cho candidate `main`.
- **Quên constructor không tham số:** instance `main` cần launcher tạo được đối tượng bằng constructor không tham số.
- **Hiểu nhầm `args`:** `args` chỉ chứa đối số truyền cho chương trình, không chứa tên lớp hay tên file.
- **Dùng cú pháp từ bản preview cũ:** compact source file trong JDK 27 là tính năng chính thức. Với console output, hãy dùng `IO.println(...)` hoặc `System.out.println(...)`; không dựa vào việc các phương thức static của `IO` được tự động import.

## 7. Tóm tắt

Một chương trình Java có thể được tổ chức theo class tường minh hoặc compact source file. Với class tường minh, package, import và các khai báo kiểu tạo nên cấu trúc của compilation unit; field, constructor và method nằm trong thân kiểu. Java launcher bắt đầu chương trình bằng một candidate `main` method có kiểu trả về `void`, có thể nhận `String[]` hoặc không nhận tham số, có thể là static hoặc instance và có một trong ba mức truy cập được hỗ trợ.

Trong JDK 27, compact source file và instance `main` method là các khả năng chính thức từ Java 25. Chúng hữu ích cho chương trình đơn file, trong khi class và package tường minh vẫn là nền tảng phù hợp cho ứng dụng có nhiều thành phần và API cần tái sử dụng.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §12.1.4 Invoke a main Method](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-12.html#jls-12.1.4)
- [Oracle Java Language Updates, Release 27 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/27/language/compact-source-files-instance-main-methods.html)
- [Oracle Java Language Changes Summary, Release 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
