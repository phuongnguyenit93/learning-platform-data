# Tổ chức lớp bằng `package` và sử dụng `import` trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `package` là gì, vì sao cần nhóm các lớp theo chức năng, và cách tên package liên hệ với cấu trúc thư mục của dự án.
- Khai báo package đúng vị trí trong tệp `.java`, nhận biết tên đầy đủ của lớp (fully qualified name) và cách khởi chạy lớp trong package.
- Phân biệt `import` kiểu đơn (`single-type import`), `import` theo yêu cầu (`on-demand import`), `static import` và cách sử dụng tên đầy đủ khi không import.
- Hiểu phạm vi truy cập `public`, package-private và giới hạn giữa package với subpackage.
- Tự biên dịch, chạy một dự án Java 17+ có nhiều tệp/lớp/package; chẩn đoán các lỗi tổ chức lớp, import, classpath thường gặp.

## 1. `package`: đặt lớp vào một không gian tên

Java cho phép nhiều lớp cùng tồn tại trong một chương trình. Khi số lớp tăng lên, nếu mọi lớp đều có tên đơn giản như `User`, `Service`, `Utils`, việc tổ chức và tránh trùng tên trở nên khó khăn.

**Package** là cách Java gom các kiểu liên quan (class, interface, enum, record, annotation...) vào một **không gian tên**. Ví dụ:

- `com.example.school.model.Student`: mô hình học sinh.
- `com.example.school.service.StudentService`: dịch vụ xử lý nghiệp vụ.
- `com.example.school.app.Main`: điểm bắt đầu chạy chương trình.

Đối với lớp `com.example.school.model.Student`:

- `Student` là **tên đơn giản** (*simple name*).
- `com.example.school.model` là **tên package**.
- `com.example.school.model.Student` là **tên đầy đủ** (*fully qualified name*).

Hai lớp `com.example.school.model.Student` và `com.example.school.api.Student` có thể cùng tên đơn giản `Student` vì thuộc hai package khác nhau. Khi dùng hai kiểu này cùng lúc, lập trình viên phải xác định kiểu nào được tham chiếu.

Package giúp phân loại mã nguồn, đặt ranh giới truy cập mặc định và tránh xung đột tên. Tuy nhiên, một package **không tự trở thành thư viện riêng, không tự cài đặt dependency và không phải cơ chế bảo mật**.

### Quy ước đặt tên package

- Thông thường dùng **chữ thường**, các thành phần phân cách bằng dấu chấm: `com.example.school.model`.
- Dự án có tên miền do tổ chức quản lý thường dùng tên miền đảo ngược để giảm khả năng trùng tên, ví dụ `org.example.project`. `com.example` chỉ là tên minh họa.
- Chọn nhóm theo trách nhiệm rõ ràng, ví dụ `model`, `service`, `app`, thay vì đặt mọi lớp vào một package rất lớn.
- Tên phân biệt chữ hoa/chữ thường; `com.example.Model` khác `com.example.model`. Không nên đặt tên package trùng tên kiểu phổ biến gây nhầm lẫn.
- **Không dùng** thành phần package là từ khóa Java (`class`, `public`, `package`...). Mỗi thành phần phải là một identifier hợp lệ.

Package tên có tiền tố giống nhau không nhất thiết có quan hệ truy cập đặc biệt. Ví dụ `com.example.school` và `com.example.school.model` là **hai package khác nhau**, không phải cha/con theo nghĩa kế thừa quyền truy cập.

## 2. Khai báo `package` trong tệp nguồn

Cú pháp:

~~~java
package com.example.school.model;

public class Student {
}
~~~

Đây là một tệp `Student.java` tối giản, có thể biên dịch độc lập. Chỉ có tối đa một khai báo `package` trong mỗi compilation unit (tệp nguồn Java thông thường). Khi có khai báo, `package` phải xuất hiện **trước các câu lệnh `import` và khai báo kiểu**, ngoại trừ khoảng trắng hoặc chú thích ở đầu tệp.

Cấu trúc thông thường:

~~~java
package com.example.app;

import java.util.List;
import static java.lang.Math.max;

public class Main {
    // Trường, constructor và phương thức
}
~~~

Đoạn trên minh họa thứ tự thành phần; phần thân `Main` chưa có phương thức `main` để chạy trực tiếp.

Nếu một tệp **không** có câu lệnh `package`, các kiểu top-level của nó thuộc **unnamed package** (thường gọi *default package*). Điều này có thể tiện với một ví dụ học tập một tệp, nhưng không nên dùng để tổ chức ứng dụng nhiều package. Đặc biệt, mã trong **named package** không thể import hoặc tham chiếu trực tiếp tới kiểu top-level trong unnamed package bằng tên đơn giản hay tên đầy đủ.

Quy tắc tên tệp thường gặp với `javac`: một kiểu top-level `public` phải được lưu trong tệp cùng tên, đúng chữ hoa/thường, chẳng hạn `public class Student` trong `Student.java`. Một tệp Java có thể chứa thêm các kiểu top-level không `public`, nhưng tách kiểu lớn thành tệp riêng thường dễ đọc và dễ bảo trì hơn.

## 3. Cấu trúc thư mục khớp package

Dự án Java thường đặt mã nguồn theo các thành phần tên package. Ví dụ nhỏ gồm hai package và ba lớp:

~~~text
school-demo/
├── src/
│   └── com/
│       └── example/
│           └── school/
│               ├── model/
│               │   ├── Student.java
│               │   └── StudentLabels.java
│               └── app/
│                   └── Main.java
└── out/                 (được tạo khi biên dịch)
~~~

Đường dẫn `src/com/example/school/model/Student.java` tương ứng dòng `package com.example.school.model;`. Thư mục `src` là **source root** do ta chọn; nó không phải một phần tên package.

Đây là quy ước tổ chức quan trọng đối với IDE, build tool và việc tìm tệp nguồn. Khi truyền tên tệp trực tiếp cho `javac`, vị trí tệp nguồn không phải lúc nào cũng bị compiler buộc phải trùng package, nhưng nên tổ chức đúng từ đầu. Khi biên dịch với `-d out`, các tệp `.class` được đặt dưới cấu trúc package tương ứng trong `out`.

## 4. Ví dụ hoàn chỉnh Java 17+: nhiều package sử dụng chung lớp

Ví dụ này minh họa ba ý: các lớp cùng package có thể dùng tên nhau mà không cần import; lớp ở package khác được import qua tên đầy đủ; các thành viên `static` cũng có thể được import.

### Tệp 1 — `src/com/example/school/model/Student.java`

~~~java
package com.example.school.model;

public final class Student {
    private final String name;

    public Student(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
    }

    public String name() {
        return name;
    }
}
~~~

`Student` là lớp top-level `public` trong package `com.example.school.model`. Constructor và phương thức `name()` cũng được khai báo `public` để mã từ package khác có thể sử dụng. Trường `name` là `private`, giúp ẩn trạng thái bên trong.

### Tệp 2 — `src/com/example/school/model/StudentLabels.java`

~~~java
package com.example.school.model;

public final class StudentLabels {
    private StudentLabels() {
        // Không tạo instance: chỉ cung cấp tiện ích static
    }

    public static String display(Student student) {
        return "Student: " + student.name();
    }
}
~~~

`StudentLabels` và `Student` ở **cùng package** nên `StudentLabels.java` có thể sử dụng tên `Student` mà **không cần** `import com.example.school.model.Student;`. Mã không được quyền truy cập trực tiếp `student.name` vì trường đó `private`; nó gọi phương thức `public name()`.

### Tệp 3 — `src/com/example/school/app/Main.java`

~~~java
package com.example.school.app;

import com.example.school.model.Student;
import com.example.school.model.StudentLabels;
import java.util.List;

import static java.lang.Math.max;

public class Main {
    public static void main(String[] args) {
        Student student = new Student("Lan");

        System.out.println(StudentLabels.display(student));

        List<String> topics = List.of("package", "import");
        System.out.println("Topics: " + String.join(", ", topics));

        System.out.println("Max: " + max(3, 8));

        System.out.println("Day: " + java.time.DayOfWeek.MONDAY);
    }
}
~~~

Các dòng đáng chú ý:

- Hai `import com.example.school.model....` cho phép viết `Student` và `StudentLabels` thay vì luôn dùng tên đầy đủ.
- `import java.util.List;` đưa tên kiểu `List` vào phạm vi tên đơn giản của tệp này. `List.of(...)` tạo một danh sách không sửa được trong Java 9+.
- `import static java.lang.Math.max;` cho phép gọi `max(3, 8)` thay vì `Math.max(3, 8)`.
- `String` và `System` thuộc `java.lang`, package được Java tự động import theo yêu cầu; không phải viết `import java.lang.String;`.
- `java.time.DayOfWeek.MONDAY` sử dụng **tên đầy đủ** mà không cần câu lệnh `import java.time.DayOfWeek;`.

### Biên dịch và chạy

Mở terminal tại thư mục **`school-demo`**, nơi có thư mục `src`. Các lệnh dưới đây dùng được trong Bash và PowerShell; `mkdir out` chỉ cần nếu `out` chưa tồn tại:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/school/model/Student.java src/com/example/school/model/StudentLabels.java src/com/example/school/app/Main.java
java -cp out com.example.school.app.Main
~~~

Kết quả từ **lệnh `java`**:

~~~text
Student: Lan
Topics: package, import
Max: 8
Day: MONDAY
~~~

Giải thích:

1. `javac` biên dịch cả ba tệp cùng nhau nên tìm được những kiểu phụ thuộc lẫn nhau.
2. `-encoding UTF-8` xác định cách giải mã tệp nguồn; `-d out` chỉ định thư mục gốc chứa `.class`. Thư mục `out` phải tồn tại trước.
3. Sau khi biên dịch, `out/com/example/school/model/` chứa `Student.class`, `StudentLabels.class`; `out/com/example/school/app/` chứa `Main.class`.
4. `java -cp out` đặt **classpath root** tại `out`; `com.example.school.app.Main` là **tên đầy đủ của lớp chứa `public static void main(String[] args)`**. Chạy `java Main` sẽ không tìm đúng lớp vì lớp thuộc named package.

Có thể biên dịch riêng `Main.java` nếu các lớp phụ thuộc đã được biên dịch và có trong classpath phù hợp; ở ví dụ này, biên dịch cả ba tệp trong một lệnh là cách dễ kiểm chứng nhất.

## 5. `import` hoạt động như thế nào?

Câu lệnh `import` là một cơ chế **giải quyết tên tại thời điểm biên dịch**. Nó cho phép viết tên kiểu hoặc thành viên `static` ở dạng ngắn trong một tệp nguồn. Nó **không**:

- Tạo đối tượng mới hoặc gọi constructor.
- Sao chép mã nguồn hay tải thư viện từ Internet.
- Làm lớp `private`/package-private tự động trở thành truy cập được.
- Thay thế việc cung cấp JAR/module phụ thuộc trên classpath/module path phù hợp.
- Tự biến các package có tên gần giống nhau thành một package duy nhất.

Các câu lệnh `import` được khai báo ở **cấp tệp nguồn**, sau `package`, trước các kiểu top-level; không đặt chúng trong thân class hoặc method.

### 5.1. Import một kiểu cụ thể: single-type import

~~~java
import java.util.List;
import java.util.ArrayList;
~~~

Sau đó có thể viết:

~~~java
List<String> names = new ArrayList<>();
names.add("Lan");
~~~

Đây là **đoạn minh họa** dùng trong thân method hoặc khối khởi tạo của một class, không phải chương trình độc lập. Nếu không import, có thể viết đầy đủ:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add("Lan");
~~~

Cả hai cách đều có ý nghĩa tương đương ở đây. Import chỉ giúp tên rõ, gọn; compiler vẫn phải biết kiểu `java.util.List` là kiểu nào. Với code production, **single-type import** thường dễ đọc và dễ kiểm soát phụ thuộc khi số kiểu sử dụng không quá lớn.

### 5.2. Import theo yêu cầu: type-import-on-demand

~~~java
import java.util.*;
~~~

Cách này cho phép dùng tên đơn giản của các **kiểu truy cập được và trực tiếp thuộc `java.util`** khi tên được tham chiếu, ví dụ `List`, `Map`, `ArrayList`.

Tuy nhiên, dấu `*` **không đệ quy**: `import java.util.*;` không import các kiểu thuộc `java.util.concurrent`, vì `java.util.concurrent` là một package riêng. Muốn dùng `ExecutorService` theo tên đơn giản, phải import `java.util.concurrent.ExecutorService` hoặc `java.util.concurrent.*`.

Java **không hỗ trợ** dạng `import com.example.**;` để gom tất cả package con, và cũng không có cú pháp `import ... as Alias` như một số ngôn ngữ khác.

### 5.3. Static import: lấy tên thành viên `static`

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

Sau đó, trong thân method có thể viết:

~~~java
double circumference = 2 * PI * 3;
int larger = max(5, 9);
System.out.println(circumference);
System.out.println(larger);
~~~

Đoạn minh họa này cho stdout:

~~~text
18.84955592153876
9
~~~

`PI` là trường `static` của `Math`; `max` là phương thức `static` của `Math`. Có thể thay bằng `Math.PI` và `Math.max(...)` mà không cần static import. Dạng `import static java.lang.Math.*;` cũng tồn tại, nhưng việc import chọn lọc giúp người đọc nhận ra nguồn của các tên ngắn. **Static import không áp dụng cho instance field/method** vì những thành viên đó cần đối tượng nhận lời gọi.

### 5.4. Package tự động có sẵn

Trong compilation unit thuộc một named package, tên các kiểu truy cập được cùng package có thể được dùng trực tiếp; các kiểu của `java.lang` cũng được import theo yêu cầu một cách ngầm định. Vì vậy:

- `StudentLabels` dùng `Student` mà không import, do cùng `com.example.school.model`.
- `Main` dùng `String`, `System` mà không khai báo import `java.lang`.
- Nhưng ở `Main`, `Student` thuộc **package khác**, nên cần import hoặc dùng tên đầy đủ.

Có thể import kiểu lồng nhau có thể truy cập qua tên kiểu chứa, chẳng hạn `import java.util.Map.Entry;`, nếu muốn dùng `Entry` trực tiếp. Đây là **member type**, không phải một subpackage `Map`.

## 6. Trùng tên khi import: nhận diện nhanh

`package` cho phép hai kiểu cùng tên đơn nhưng khác tên đầy đủ, ví dụ `java.util.Date` và `java.sql.Date`. Trong cùng một compilation unit, **không được single-type import cả hai**:

~~~java
import java.util.Date;
import java.sql.Date; // Lỗi: hai single-type imports cùng tên Date.
~~~

Cách xử lý thông dụng là chỉ import kiểu dùng thường xuyên, còn kiểu thứ hai viết **tên đầy đủ**; ví dụ `Date` và `java.sql.Date` tại nơi sử dụng. Nếu dùng hai on-demand imports `java.util.*` và `java.awt.*`, tên `List` có thể trở nên mơ hồ. Chọn rõ `java.util.List` hoặc import kiểu cụ thể.

Điểm chính ở bài này: import chỉ tác động đến **khả năng dùng tên trong tệp nguồn**, không đổi danh tính package hay quyền truy cập. Phần xử lý *simple name*, *qualified name*, shadowing và các trường hợp nhập nhằng là trọng tâm riêng của bài về trùng tên lớp.


## 7. Package và quyền truy cập

Package là ranh giới quan trọng trong **kiểm tra truy cập của Java**. Một số khái niệm cần phân biệt:

| Thành phần | Có thể sử dụng từ package khác? |
| --- | --- |
| Kiểu top-level `public` | Có, nếu kiểu được nhìn thấy và các điều kiện truy cập/module khác thỏa mãn |
| Kiểu top-level không ghi `public` (package-private) | Không truy cập trực tiếp từ package khác |
| Thành viên `public` của kiểu có thể truy cập | Có, theo các điều kiện truy cập thông thường |
| Thành viên không ghi access modifier (package-private) | Chỉ từ các kiểu cùng package |
| Thành viên `private` | Giới hạn theo quy tắc private của Java; không trở thành public khi import |
| Thành viên `protected` | Có quyền trong cùng package và những trường hợp kế thừa thích hợp ở package khác |

Lưu ý: từ Java 11, quy tắc `private` có liên quan đến các lớp lồng nhau thuộc cùng *nest*; để học package, điều quan trọng là `import` không thay đổi quyền truy cập.

Ví dụ, kiểu sau **không có `public`**:

~~~java
package com.example.school.model;

class InternalCode {
    static String value() {
        return "internal";
    }
}
~~~

Mã trong `com.example.school.model` có thể sử dụng `InternalCode` nếu thỏa điều kiện truy cập thông thường. Mã trong `com.example.school.app` không được tham chiếu trực tiếp tới kiểu package-private này bằng `import`, kể cả cố gắng dùng tên đầy đủ. Ngay cả `com.example.school.model.extra` cũng là **package khác** nên không tự nhận quyền truy cập package-private của `com.example.school.model`.

Với kiểu `public Student` trong ví dụ chính, nếu constructor bị bỏ `public`, mã trong package `app` không thể gọi `new Student("Lan")` từ một constructor chỉ có quyền package-private. Muốn tạo đối tượng từ package khác, vừa cần kiểu được phép truy cập, vừa cần constructor/phương thức cần dùng được phép truy cập.

**Giới hạn của Java module system:** trong một ứng dụng dùng **named modules** (Java 9+), quyền truy cập còn phụ thuộc `requires` và `exports` trong `module-info.java`. Tên `public` không có nghĩa là mọi module bên ngoài đều nhìn thấy package đó. Import không thay thế khai báo module. Ví dụ trong bài sử dụng classpath thông thường, không yêu cầu cấu hình module.

## 8. Package, classpath và thư mục: ba khái niệm khác nhau

Người mới học thường lẫn `package`, `import` và `classpath`:

| Khái niệm | Vai trò |
| --- | --- |
| `package com.example.school.app;` | Đặt lớp vào không gian tên `com.example.school.app` |
| `import com.example.school.model.Student;` | Cho phép compiler giải quyết tên ngắn `Student` trong tệp |
| `-cp out` / `-classpath out` | Báo cho công cụ nơi tìm những lớp/thư viện đã biên dịch khi chạy (và có thể khi biên dịch với `javac -cp`) |
| `-d out` | Báo cho `javac` nơi đặt các tệp `.class` tạo ra |
| Dependency/JAR/module path | Cung cấp những lớp thực sự cần thiết từ thư viện/module bên ngoài |

Nếu có `Main.class` nằm tại `out/com/example/school/app/Main.class`, Java cần classpath root là **`out`**, sau đó dùng tên lớp **`com.example.school.app.Main`**. Không nhập đường dẫn tệp `out/com/example/school/app/Main.class` thay cho tên lớp vào lệnh `java`.

Nếu dùng IDE, Maven hay Gradle, các công cụ đó thường quản lý source roots, classpath và biên dịch thay bạn. Nhưng bản chất tên package, import, quyền truy cập và tên đầy đủ vẫn như trên. Một import hợp lệ về cú pháp vẫn có thể lỗi nếu thư viện định nghĩa kiểu ấy chưa được đưa vào dependency tương ứng.

## 9. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `class, interface, enum, or record expected` quanh `import` | Đặt `import` sai vị trí, chẳng hạn bên trong class hoặc sau khi đã khai báo kiểu | Đặt `package` ở đầu, tiếp theo là `import`, cuối cùng là khai báo kiểu |
| `package ... does not exist` | Sai tên package, thiếu file nguồn/class đã biên dịch, hoặc thiếu classpath/dependency | Xác minh package trong tệp, đường dẫn đầu vào và các dependency |
| `cannot find symbol: class Student` | Thiếu import, sai tên, sai package hoặc compiler chưa tìm được kiểu | Kiểm tra tên đầy đủ, import và classpath/source files |
| `... is not public ... cannot be accessed from outside package` | Kiểu top-level là package-private | Dùng API public thích hợp, hoặc điều chỉnh thiết kế/quyền truy cập khi thực sự cần |
| `... has private access` | Đang truy cập trực tiếp trường hoặc phương thức `private` | Dùng API công khai của lớp thay vì cố import |
| `reference to List is ambiguous` | Hai on-demand imports mang vào các kiểu cùng tên | Import kiểu cụ thể hoặc dùng tên đầy đủ |
| `class Main is public, should be declared in a file named Main.java` | Tên tệp không trùng với kiểu `public` | Đổi tên thành `Main.java` đúng chữ hoa/thường |
| `Could not find or load main class ...` | Sai tên đầy đủ khi gọi `java`, sai classpath root hoặc chưa biên dịch | Chạy `java -cp out com.example.school.app.Main` sau khi biên dịch thành công |
| Import `java.util.*` nhưng không tìm thấy `ExecutorService` | Dấu `*` không import subpackage | Import `java.util.concurrent.ExecutorService` |
| Có import nhưng chạy bị `NoClassDefFoundError` | Lớp phụ thuộc không có ở runtime classpath/module path hoặc có vấn đề liên kết | Kiểm tra các JAR/module thực tế lúc chạy; import chỉ hỗ trợ biên dịch |

Khi chẩn đoán, trước hết đọc **lỗi đầu tiên** của compiler rồi kiểm tra tên package và thư mục classpath. Một lỗi import có thể kéo theo nhiều lỗi khác. Không nên sửa mọi dòng được báo lỗi trước khi xử lý nguyên nhân gốc.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Tệp `src/org/example/model/Book.java` có dòng `package org.example.model;`. Tên đầy đủ của lớp top-level `public class Book` là gì?  
**Đáp án:** `org.example.model.Book`. `src` chỉ là source root, không thuộc tên đầy đủ.

**Câu 2.** `com.example.model.Book` có tự truy cập được một kiểu package-private trong `com.example.model.internal` không?  
**Đáp án:** Không. Hai tên package khác nhau, bất kể quan hệ tiền tố.

**Câu 3.** `import java.util.*;` có giúp dùng trực tiếp `ExecutorService` không?  
**Đáp án:** Không. Phải import `java.util.concurrent.ExecutorService` hoặc dùng tên đầy đủ vì `java.util.concurrent` là package khác.

**Câu 4.** Khi đã `import com.example.school.model.Student;`, câu lệnh import có tạo đối tượng `Student` không?  
**Đáp án:** Không. Import chỉ rút gọn cách tham chiếu tên kiểu. Đối tượng được tạo khi thực thi thao tác khởi tạo như `new Student("Lan")`.

**Câu 5.** Muốn chạy `Main.class` đã biên dịch tại `out/com/example/school/app/Main.class` thì gõ lệnh nào ở thư mục gốc dự án?  
**Đáp án:** `java -cp out com.example.school.app.Main`.

**Câu 6.** Trong ví dụ hoàn chỉnh, vì sao `StudentLabels` sử dụng được `Student` mà không import, nhưng `Main` cần import?  
**Đáp án:** `StudentLabels` thuộc cùng package `com.example.school.model` với `Student`; `Main` thuộc `com.example.school.app`, một package khác.

## Ghi nhớ

- **`package` xác định lớp thuộc không gian tên nào**; tên package thường phản ánh thư mục nguồn và xác định tên đầy đủ của lớp.
- **`import` chỉ giúp sử dụng tên ngắn trong tệp Java**; không tải thư viện, không tạo đối tượng và không thay đổi quyền truy cập.
- Các kiểu trong **cùng package** và các kiểu thuộc `java.lang` có thể dùng tên đơn giản mà không cần viết import thông thường.
- **Subpackage là package khác**; wildcard import không đệ quy, package-private không mở rộng sang subpackage.
- **Biên dịch và chạy** cần source files, output root/classpath và tên lớp đầy đủ chính xác; một import đúng cú pháp vẫn không thay thế dependency thực sự.
