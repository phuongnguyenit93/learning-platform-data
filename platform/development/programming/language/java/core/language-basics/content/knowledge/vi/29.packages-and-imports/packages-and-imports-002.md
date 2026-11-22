# Khai báo `package` và cấu trúc thư mục tương ứng trong Java

> **Java core — language-basics / Package và import**  
> **Yêu cầu:** JDK 17+, không dùng thư viện ngoài.  
> **Mục tiêu:** Khai báo `package` đúng vị trí trong file Java; tổ chức các tệp `.java` theo thư mục tương ứng; biên dịch bằng `javac -d`, chạy bằng tên lớp đầy đủ và classpath; phân biệt package với thư mục, import và quyền truy cập.

## 1. `package` xác định không gian tên của lớp

Một *package* nhóm các kiểu Java có liên quan và tạo không gian tên, giúp tránh trùng tên giữa các lớp của ứng dụng. Ví dụ:

~~~java
package vn.learn.demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

Ở đây tên lớp đầy đủ (*fully qualified name*, FQN) là `vn.learn.demo.Main` chứ không chỉ `Main`. Khai báo `package vn.learn.demo;` có dấu chấm giữa các thành phần và **kết thúc bằng dấu chấm phẩy**.

Mỗi tệp `.java` có tối đa **một** khai báo `package`. Nếu không có khai báo này, các top-level type trong tệp nằm trong *unnamed package* (thường gọi là *default package*). Điều này tiện cho thử nghiệm rất nhỏ nhưng không được khuyến khích cho chương trình nhiều tệp hoặc cần tái sử dụng từ các package có tên.

**Tên package phân biệt chữ hoa/chữ thường.** Theo thông lệ đặt tên bằng chữ thường, ví dụ `vn.learn.demo` hoặc theo tên miền đảo ngược `com.example.app`. Không được sử dụng từ khóa Java làm một thành phần tên package.

## 2. Thứ tự `package`, `import` và khai báo kiểu

Trong tệp Java có package, bố cục phổ biến như sau:

~~~java
// Có thể viết comment và khoảng trắng ở đây.
package vn.learn.demo;

import java.util.Arrays;
import vn.learn.demo.tools.Counter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Arrays.toString(new int[] {1, 2}));
    }
}
~~~

Quy tắc cần nhớ:

1. `package ...;` là khai báo package của compilation unit, đặt **trước mọi khai báo `import` và top-level type**; comment/khoảng trắng có thể xuất hiện trước.
2. Nếu cần `import`, chúng đặt **sau `package`** và **trước các khai báo lớp/interface/enum/record**.
3. Một tệp có thể chứa các top-level type phù hợp, nhưng khi có `public class Main` trong cách tổ chức thông thường, lưu tệp thành `Main.java`.
4. `import` không đổi package chứa `Main`; nó chỉ giúp dùng tên ngắn của kiểu hoặc thành viên static được nhập.
5. `java.lang` được nhập tự động cho các kiểu quen thuộc như `String` và `System`.

**Sai thứ tự:**

~~~java
// SAI — không thể đặt import trước khai báo package:
// import java.util.List;
// package vn.learn.demo;
~~~

Tên trong `package` không phải chuỗi ký tự có dấu ngoặc kép. Viết `package "vn.learn.demo";` sẽ không biên dịch.

## 3. Cấu trúc thư mục nguồn tương ứng

Thói quen chuẩn là đổi các dấu chấm của tên package thành dấu phân cách thư mục. Với `vn.learn.demo`, tệp `Main.java` nên nằm ở:

`src/vn/learn/demo/Main.java`

Ví dụ cấu trúc nguồn và đầu ra biên dịch:

~~~text
project/
├── src/
│   └── vn/
│       └── learn/
│           └── demo/
│               ├── Main.java
│               ├── Greeter.java
│               └── tools/
│                   └── Counter.java
└── out/                      (thư mục chứa .class sau biên dịch)
~~~

| Khai báo trong tệp | Đường dẫn nguồn được khuyến nghị |
| --- | --- |
| `package vn.learn.demo;` | `src/vn/learn/demo/Main.java` |
| `package vn.learn.demo;` | `src/vn/learn/demo/Greeter.java` |
| `package vn.learn.demo.tools;` | `src/vn/learn/demo/tools/Counter.java` |

`src` là **thư mục gốc mã nguồn** trong ví dụ, không phải thành phần của tên package. `Main.java` khai báo `vn.learn.demo` chứ không phải `src.vn.learn.demo`.

**Đây là quy ước tổ chức quan trọng của công cụ**, không phải quy tắc cú pháp bắt buộc khiến mọi tệp Java ở sai thư mục đều không thể được `javac` biên dịch khi chỉ rõ đường dẫn tệp. Tuy vậy, tuân theo cấu trúc này giúp trình biên dịch, IDE và build tool tìm đúng mã nguồn, tránh nhầm lẫn khi dự án lớn.

## 4. Ví dụ Java 17+ với ba tệp thuộc hai package

Tạo đúng ba tệp sau dưới thư mục `project`. Đây là **một ví dụ runnable thống nhất**, không cần bất kỳ thư viện ngoài nào.

**Tệp 1 — `src/vn/learn/demo/Greeter.java`**

~~~java
package vn.learn.demo;

// Không ghi public: lớp top-level chỉ truy cập trực tiếp trong package.
final class Greeter {
    private Greeter() {
    }

    static String hello(String name) {
        return "Xin chào, " + name;
    }
}
~~~

**Tệp 2 — `src/vn/learn/demo/tools/Counter.java`**

~~~java
package vn.learn.demo.tools;

public final class Counter {
    private int value;

    public Counter(int initial) {
        this.value = initial;
    }

    public int value() {
        return value;
    }

    public void add(int amount) {
        value += amount;
    }
}
~~~

**Tệp 3 — `src/vn/learn/demo/Main.java`**

~~~java
package vn.learn.demo;

import vn.learn.demo.tools.Counter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("mainPackage=" + Main.class.getPackageName());
        System.out.println("greeting=" + Greeter.hello("Lan"));

        Counter counter = new Counter(2);
        System.out.println("start=" + counter.value());
        counter.add(3);
        System.out.println("afterAdd=" + counter.value());

        System.out.println("toolsPackage=" + Counter.class.getPackageName());
        System.out.println("counterClass=" + Counter.class.getName());
    }
}
~~~

Tại sao ví dụ hoạt động?

- `Main` và `Greeter` khai báo **cùng** `package vn.learn.demo;` nên `Main` dùng được lớp package-private `Greeter` mà không cần import.
- `Counter` ở package **khác** là `vn.learn.demo.tools`, nên `Main` phải sử dụng tên đầy đủ hoặc `import` hợp lệ. `Counter` và constructor/method dùng từ ngoài package đều được khai báo `public`.
- `getPackageName()` cho thấy tên package tại runtime; `Counter.class.getName()` cho tên lớp đầy đủ.
- `private int value` của `Counter` không được truy cập trực tiếp từ `Main`; `value()` và `add(...)` cung cấp API.

## 5. Biên dịch đúng thư mục đầu ra và chạy bằng classpath

Chạy lệnh từ thư mục **`project`** chứa `src`. Trước hết tạo thư mục đầu ra `out` nếu chưa tồn tại.

Với **Bash/Linux/macOS**:

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out src/vn/learn/demo/Greeter.java src/vn/learn/demo/tools/Counter.java src/vn/learn/demo/Main.java
java -cp out vn.learn.demo.Main
~~~

Với **Windows PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/vn/learn/demo/Greeter.java src/vn/learn/demo/tools/Counter.java src/vn/learn/demo/Main.java
java -cp out vn.learn.demo.Main
~~~

**Expected stdout của lệnh `java -cp out vn.learn.demo.Main` (chính xác):**

~~~text
mainPackage=vn.learn.demo
greeting=Xin chào, Lan
start=2
afterAdd=5
toolsPackage=vn.learn.demo.tools
counterClass=vn.learn.demo.tools.Counter
~~~

Lệnh `javac` biên dịch thành các tệp `.class` dưới `out`:

~~~text
out/
└── vn/
    └── learn/
        └── demo/
            ├── Main.class
            ├── Greeter.class
            └── tools/
                └── Counter.class
~~~

**Ý nghĩa lệnh:**

| Thành phần | Công dụng |
| --- | --- |
| `javac` | Biên dịch nguồn Java thành bytecode `.class` |
| `-encoding UTF-8` | Đọc nguồn có tiếng Việt đúng bộ mã |
| `-d out` | Chọn **gốc thư mục đầu ra**, nơi `javac` tạo nhánh package tương ứng |
| `java -cp out` | Đưa gốc thư mục lớp biên dịch vào classpath |
| `vn.learn.demo.Main` | Tên lớp đầy đủ chứa `main`, không phải đường dẫn tệp |

Với `javac -d out`, thư mục `out` cần tồn tại; trình biên dịch tạo các **thư mục package bên trong** khi cần. Khi chạy, classpath phải trỏ đến **gốc phía trên `vn`** (`out`), không trỏ trực tiếp đến `out/vn/learn/demo`. Khi dùng `java -cp out ...`, không truyền đuôi `.class`.

## 6. Package con không tự thuộc cùng package về quyền truy cập

Tên `vn.learn.demo.tools` có vẻ nằm “dưới” `vn.learn.demo`, nhưng xét quyền truy cập, Java xem chúng là **hai package khác nhau**.

~~~java
// Giả sử đặt trong package vn.learn.demo:
class InternalHelper {
    static String code() {
        return "internal";
    }
}
~~~

Lớp ở `vn.learn.demo.tools` **không được tự động** gọi `InternalHelper.code()` vì `InternalHelper` là lớp top-level package-private của một package khác.

| Trường hợp | Kết quả |
| --- | --- |
| Hai lớp khai báo `package vn.learn.demo;` | Cùng package, có thể truy cập thành viên package-private phù hợp |
| Một lớp `vn.learn.demo`, một lớp `vn.learn.demo.tools` | Khác package, không tự có quyền package-private |
| `import vn.learn.demo.tools.Counter;` | Cho phép dùng tên ngắn `Counter` nếu kiểu và thành viên được truy cập hợp lệ |
| `import vn.learn.demo.*;` | Không tự nhập các kiểu trong `vn.learn.demo.tools` |
| Field `private` của `Counter` | Không thể truy cập trực tiếp từ lớp ngoài không có quyền |

**Import không cấp thêm quyền truy cập.** Ví dụ `import vn.learn.demo.tools.Counter;` không cho phép `Main` đọc `counter.value` vì field vẫn `private`.

Một lớp `public` và constructor `public` có thể được dùng xuyên package khi môi trường/module cho phép. Với các chương trình nhập môn không có `module-info.java` như ví dụ trên, classpath là cơ chế đơn giản nhất.

## 7. Lỗi phổ biến về package, đường dẫn và lệnh chạy

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Could not find or load main class Main` | `Main` thuộc package có tên, không phải unnamed package | Dùng `java -cp out vn.learn.demo.Main` |
| `ClassNotFoundException: vn.learn.demo.Main` | Classpath sai gốc hoặc chưa biên dịch lớp | Kiểm tra `out/vn/learn/demo/Main.class`, dùng `-cp out` |
| `package ... does not exist` khi biên dịch | Chưa đưa mã nguồn/dependency hoặc classpath phù hợp vào `javac` | Biên dịch đủ các tệp, kiểm tra tên package |
| `cannot find symbol` cho `Counter` | Thiếu import hoặc dùng sai tên kiểu | `import vn.learn.demo.tools.Counter;` hoặc tên đầy đủ |
| `... is not public; cannot be accessed from outside package` | Lớp hoặc thành viên package-private được gọi khác package | Thiết kế API public hợp lệ hoặc đặt mã nội bộ cùng package |
| `class Main is public, should be declared in a file named Main.java` | Tên file không khớp public top-level class | Đặt đúng `Main.java` |
| Chạy `java -cp out/vn/learn/demo Main` | Chọn nhầm **nhánh package** làm classpath root | Chọn gốc `out` và tên lớp đầy đủ |
| `mkdir out` chưa chạy, `javac -d out` lỗi | Thư mục đầu ra chưa tồn tại | Tạo `out` trước khi biên dịch |
| Chuyển `Main.java` sang package khác nhưng giữ `java ...vn.learn.demo.Main` | Tên package trong nguồn, thư mục output và FQN không thống nhất | Cập nhật khai báo, vị trí nguồn và lệnh chạy |

Java phân biệt chữ hoa/chữ thường trong định danh tên package và class. Đặc biệt trên hệ điều hành có filesystem phân biệt hoa/thường, `Demo` và `demo` là tên khác nhau.

**Đừng sửa bằng cách xóa bừa khai báo `package`.** Khi lỗi nằm ở classpath hoặc cây thư mục, việc bỏ `package` thay đổi tên đầy đủ và cấu trúc của cả chương trình.

## 8. Checklist thực hành và bài tập

**Checklist chạy chương trình nhiều package:**

1. Mỗi tệp khai báo đúng `package ...;` trước `import` và lớp.
2. Cây `src` phản ánh tên package theo từng phần, ví dụ `vn/learn/demo`.
3. File `Main.java` chứa `public class Main` và phương thức `main` hợp lệ.
4. Các kiểu dùng xuyên package có quyền truy cập phù hợp; `import` không thay thế `public`.
5. Tạo thư mục `out`, dùng `javac -d out` biên dịch đầy đủ mã nguồn.
6. Chạy `java -cp out vn.learn.demo.Main` từ gốc project và kiểm tra đúng stdout.

**Bài 1.** Tạo `src/com/example/hello/Main.java` có `package com.example.hello;`. Biên dịch bằng `javac -d out` và chạy bằng FQN tương ứng.

**Bài 2.** Tạo thêm `src/com/example/hello/Message.java` cùng package; cho lớp `Message` không ghi `public` và gọi phương thức package-private từ `Main`.

**Bài 3.** Chuyển `Message` sang `com.example.hello.util`. Giải thích vì sao giờ `Main` cần kiểu có thể truy cập từ package khác và có thể cần `import`.

**Bài 4.** Cố chạy `java -cp out Main` sau khi có khai báo package. Đọc lỗi, rồi sửa thành tên lớp đầy đủ.

**Bài 5.** Đổi `package vn.learn.demo.tools;` trong `Counter.java` thành một package khác. Cập nhật đường dẫn nguồn, `import` và lệnh chạy tương ứng; dự đoán cây output `.class`.

### Ghi nhớ

**`package` xác định tên đầy đủ của kiểu; cấu trúc nguồn `src/a/b/C.java` nên khớp `package a.b;`.** Dùng `javac -d out` để tổ chức các `.class` theo package, rồi chạy bằng `java -cp out a.b.C`. `import` chỉ giúp dùng tên ngắn, không thay đổi package hoặc quyền truy cập; package con vẫn là một package khác.
