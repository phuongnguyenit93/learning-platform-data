# Tên đơn giản, tên đầy đủ và xử lý trùng tên lớp trong Java

Khi chương trình có nhiều lớp, câu hỏi “`Student` là lớp nào?” không thể trả lời chỉ bằng một từ `Student`. Java tổ chức lớp theo **package** và có quy tắc xác định một **tên đơn giản (simple name)** đang chỉ đến kiểu nào. Hiểu những quy tắc này giúp viết `import` đúng, phân biệt lớp cùng tên từ hai thư viện, đọc lỗi biên dịch và tránh xung đột khi dự án lớn dần.

Bài học tập trung vào tên lớp và các kiểu tham chiếu khai báo trong Java; quy tắc tương tự áp dụng ở nhiều chỗ cho interface, enum, record và annotation. Các ví dụ dùng **Java 17 trở lên**.

## 1. Tên đơn giản và tên đủ điều kiện

Cho khai báo:

~~~java
package com.example.school;

public class Student {
}
~~~

- **Tên đơn giản:** `Student` — một định danh duy nhất, không chứa phần package.
- **Tên đủ điều kiện (fully qualified name):** `com.example.school.Student` — gồm tên package và tên lớp cấp cao nhất.
- **Tên package:** `com.example.school` — không phải một lớp, mà là không gian tên chứa lớp.

Hai dòng sau cùng có thể nói đến một lớp, nếu `Student` tại vị trí đó được Java phân giải thành `com.example.school.Student`:

~~~java
Student student = new Student();
com.example.school.Student another = new com.example.school.Student();
~~~

*Đây là đoạn minh họa được đặt trong phạm vi đã có quyền truy cập đến lớp `Student`; bản thân hai câu lệnh không phải một tệp Java hoàn chỉnh.*

Dạng đầu ngắn, dễ đọc nhưng phụ thuộc phạm vi của tên `Student`. Dạng sau chỉ rõ package, nên có ích khi nhiều lớp cùng tên xuất hiện trong chương trình.

| Cách viết | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên đơn giản | `Student` | Java xác định kiểu phù hợp dựa trên khai báo, phạm vi và import |
| Tên đủ điều kiện của lớp cấp cao nhất | `com.example.school.Student` | Chỉ rõ lớp `Student` thuộc package nào |
| Tên đơn giản của lớp thành viên | `Entry` | Có thể dùng khi kiểu thành viên nằm trong phạm vi hoặc được import phù hợp |
| Tên dạng phân cấp của lớp thành viên | `java.util.Map.Entry` | Tên canonical của kiểu thành viên `Entry` trong `Map` |

Trong tài liệu Java, **qualified name** là tên có các thành phần nối bằng dấu chấm; **fully qualified name** và **canonical name** thường trùng nhau đối với lớp cấp cao nhất có tên trong package. Với kiểu lồng nhau, cần phân biệt thêm **binary name** (xem mục 8); không phải mọi chuỗi trả về bởi API phản chiếu đều là tên hợp lệ để viết trực tiếp trong mã nguồn.

## 2. Vì sao có thể tồn tại nhiều lớp cùng tên?

Ví dụ dự án có hai lớp:

~~~text
school.Student
company.Student
~~~

Chúng đều có **tên đơn giản** `Student`, nhưng nằm ở **hai package khác nhau**, vì thế là hai kiểu khác nhau. Trong chương trình, có thể dùng cả hai một cách hợp lệ:

~~~java
school.Student learner = new school.Student("An");
company.Student employee = new company.Student("Binh");
~~~

Hai đối tượng không cùng kiểu chỉ vì tên đơn giản giống nhau. Trình biên dịch phải biết **đúng lớp** để kiểm tra constructor, phương thức, trường, quyền truy cập và phép gán.

Ngược lại, không thể định nghĩa hai lớp cấp cao nhất có **cùng tên trong cùng một package** của chương trình: ví dụ hai khai báo khác nhau đều là `school.Student` sẽ gây xung đột kiểu ở thời điểm biên dịch/tổ chức nguồn. Cũng không thể khai báo hai lớp cấp cao nhất đều tên `Student` trong cùng một compilation unit rồi coi chúng là hai kiểu riêng biệt.

Package giúp chia không gian tên. Dấu chấm giữa các thành phần package biểu thị cấu trúc tên phân cấp, nhưng không có nghĩa package con tự động kế thừa quyền truy cập hoặc các kiểu từ package cha.

## 3. Phân giải tên đơn giản: vì sao compiler chọn đúng một kiểu?

Một tệp có thể khai báo `package`, rồi các câu `import` trước phần khai báo class. Ở bài này điều quan trọng là **`Student`, `List` hoặc `Date` tại mỗi vị trí đang chỉ đến kiểu nào**, chứ không phải dạy lại cơ chế tổ chức thư mục.

Các nguồn tên thường gặp gồm: kiểu khai báo trong lexical scope (member/local types), kiểu cùng package, `single-type import`, `type-import-on-demand` và những kiểu trong `java.lang`. Chúng **không phải một thuật toán thử theo thứ tự cố định**: JLS có quy tắc cụ thể về scope, shadowing, imports và ambiguity. Ví dụ, single-type import có thể ưu tiên hơn on-demand imports ở nơi không có khai báo gần hơn gây xung đột.

~~~java
import java.util.List;
import java.awt.*;

class NameResolution {
    List<String> names; // java.util.List, không phải java.awt.List
}
~~~

Đây là lớp minh họa hợp lệ; không có `main` để chạy. `java.awt.*` không tự biến `List` thành tên mơ hồ khi có single-type import cụ thể `java.util.List`.

Ngược lại, **hai single-type imports** cho hai kiểu khác nhau nhưng cùng simple name bị từ chối ngay khi biên dịch, còn hai on-demand imports có thể dẫn đến ambiguity khi tên trùng thật sự được dùng. Khi cần hai kiểu cùng tên, chọn tên đầy đủ cho ít nhất một kiểu.

Imports chỉ có phạm vi trong **compilation unit đang khai báo**: import `school.Student` ở một file không khiến file khác cùng package tự động nhập `school.Student`. Wildcard import `java.util.*` cũng không bao gồm subpackage `java.util.concurrent`. Những chi tiết này giúp bạn chẩn đoán chính xác “cannot find symbol” hoặc “reference is ambiguous” thay vì thêm imports tùy ý.


## 4. Ví dụ hoàn chỉnh: hai lớp Student khác package

Hãy tạo bốn thư mục/tệp theo cấu trúc:

~~~text
name-demo/
└── src/
    ├── school/
    │   └── Student.java
    ├── company/
    │   └── Student.java
    └── app/
        └── NameConflictDemo.java
~~~

### Tệp `src/school/Student.java`

~~~java
package school;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String description() {
        return "School: " + name;
    }
}
~~~

### Tệp `src/company/Student.java`

~~~java
package company;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String description() {
        return "Company: " + name;
    }
}
~~~

Hai tệp khai báo `public class Student`, nhưng chúng nằm ở hai package riêng và có **hai tên đủ điều kiện khác nhau**. Java cho phép cả hai tồn tại trong cùng ứng dụng.

### Tệp `src/app/NameConflictDemo.java`

~~~java
package app;

import school.Student;

public class NameConflictDemo {
    public static void main(String[] args) {
        Student learner = new Student("An");
        company.Student employee = new company.Student("Binh");

        System.out.println(learner.description());
        System.out.println(employee.description());
        System.out.println(learner.getClass().getName());
        System.out.println(employee.getClass().getName());
    }
}
~~~

Ở đây, `import school.Student;` làm cho `Student` ở hai dòng đầu của `main` được hiểu là `school.Student`. Để dùng kiểu còn lại trong cùng tệp, viết `company.Student` khi khai báo biến và tạo đối tượng.

Mở terminal tại thư mục **`name-demo`**, chạy:

~~~bash
javac -encoding UTF-8 -d out src/school/Student.java src/company/Student.java src/app/NameConflictDemo.java
java -cp out app.NameConflictDemo
~~~

Stdout chính xác:

~~~text
School: An
Company: Binh
school.Student
company.Student
~~~

Giải thích lệnh:

- `javac` biên dịch ba tệp; `-d out` đặt tệp `.class` vào cây thư mục kết quả theo package, ví dụ `out/school/Student.class`, `out/company/Student.class`, `out/app/NameConflictDemo.class`.
- `java -cp out app.NameConflictDemo` đặt `out` trên classpath và chạy lớp có tên đủ điều kiện `app.NameConflictDemo`.
- Phương thức `getClass().getName()` cho biết tên của kiểu runtime; ở hai lớp cấp cao nhất này, kết quả chính là `school.Student` và `company.Student`.
- Không thể chạy đúng lớp `app.NameConflictDemo` bằng cách mặc định gõ `java NameConflictDemo` trong cấu trúc output trên: JVM cần tên đủ điều kiện của main class thuộc package `app`.

Đường dẫn nguồn `src/school/Student.java` và khai báo `package school;` tương ứng theo **quy ước tổ chức dự án**, giúp compiler và công cụ build tìm lớp. Tên package được quyết định bởi dòng `package` trong nguồn, không phải chỉ do tên thư mục chứa tệp. Với cấu hình biên dịch phù hợp, `javac -d` bố trí output theo package.

## 5. Khi hai import có cùng tên đơn giản

Giả sử trong `src/app/NameConflictDemo.java` ta viết:

~~~java
import school.Student;
import company.Student;
~~~

**Đây là ví dụ lỗi cố ý, không ghép hai dòng này vào chương trình chạy ở mục 4.** Hai lệnh single-type import khác nhau cùng đưa tên đơn giản `Student` vào một compilation unit. Trình biên dịch sẽ báo lỗi, **kể cả khi chưa sử dụng tên `Student`**.

Java **không hỗ trợ alias import** như cú pháp `import company.Student as CompanyStudent;`. Có ba cách dễ hiểu để xử lý:

1. Import kiểu dùng thường xuyên: `import school.Student;`.
2. Viết tên đủ điều kiện cho kiểu còn lại: `company.Student`.
3. Nếu code liên tục phải dùng hai kiểu cùng tên và rất khó đọc, cân nhắc thiết kế/tên lớp theo ý nghĩa nghiệp vụ, nhưng chỉ đổi tên khi bạn kiểm soát được mã nguồn và có lý do rõ ràng.

Có thể dùng **cả hai kiểu bằng tên đủ điều kiện**, không import kiểu nào:

~~~java
school.Student learner = new school.Student("An");
company.Student employee = new company.Student("Binh");
~~~

Các dòng này minh họa cách viết bên trong một phương thức đã có quyền truy cập tới hai lớp; trong ví dụ ở mục 4, cả hai class đều `public`.

## 6. Dấu sao không tự giải quyết xung đột

Một trường hợp khác là:

~~~java
import java.util.*;
import java.sql.*;

class AmbiguousExample {
    Date value;
}
~~~

**Đoạn mã này cố ý gây lỗi biên dịch**: cả `java.util` và `java.sql` đều có lớp `Date` công khai. Hai dòng import `*` tự chúng không gây lỗi; khi dùng tên đơn giản `Date`, compiler không có một kiểu duy nhất để chọn và báo tham chiếu **ambiguous**.

Cách khắc phục là chỉ rõ lựa chọn. Ví dụ hoàn chỉnh, tạo tệp **`DateNameDemo.java`**:

~~~java
import java.util.Date;

public class DateNameDemo {
    public static void main(String[] args) {
        Date generalDate = new Date(0);
        java.sql.Date sqlDate = new java.sql.Date(0);

        System.out.println(generalDate.getClass().getName());
        System.out.println(sqlDate.getClass().getName());
    }
}
~~~

Biên dịch và chạy ở thư mục chứa tệp:

~~~bash
javac DateNameDemo.java
java DateNameDemo
~~~

Stdout:

~~~text
java.util.Date
java.sql.Date
~~~

Dòng `import java.util.Date;` cho phép dùng `Date` ở dạng ngắn để chỉ `java.util.Date`; `java.sql.Date` được viết đầy đủ ở nơi cần. Đây là ví dụ về phân giải tên lớp; trong ứng dụng hiện đại, API `java.time` thường thích hợp hơn cho việc biểu diễn ngày, giờ, và không nên tùy tiện tráo đổi hai loại `Date`.

Nếu viết `import java.util.Date;` đồng thời `import java.sql.*;`, một tham chiếu đơn giản `Date` thường được phân giải về kiểu được **single-type import rõ ràng** `java.util.Date`, miễn không có khai báo khác ở phạm vi cao hơn làm thay đổi kết quả. Vấn đề của import `*` là khả năng xuất hiện xung đột khi hai nguồn ngang hàng cùng cung cấp một tên đang được dùng.

Một phương án đọc rõ hơn khi làm việc với thư viện lớn là ưu tiên **import tường minh** thay vì luôn dùng `*`, song import tường minh vẫn phải tránh trùng tên đơn giản giữa hai single-type import.

## 7. Tên cùng package, java.lang và shadowing

### Các lớp cùng package

Nếu `app/Helper.java` khai báo:

~~~java
package app;

public class Helper {
    public static String label() {
        return "OK";
    }
}
~~~

Thì một tệp khác cũng có `package app;` thường có thể viết `Helper.label()` mà không cần `import app.Helper;`, vì `Helper` là kiểu của cùng package. Trong mã ở package khác, muốn truy cập kiểu `Helper` thì lớp phải có mức truy cập phù hợp và có thể dùng `import app.Helper;` hoặc tên `app.Helper`.

### Các lớp của java.lang

`String`, `Object`, `System`, `Math` là những tên đơn giản quen thuộc được dùng không cần import:

~~~java
String text = "Java";
System.out.println(text);
~~~

Về thực chất, các tên này thuộc package `java.lang`; khi cần ghi rõ, `java.lang.String` cũng là một tên kiểu hợp lệ.

### Khi tên bị che bởi khai báo gần hơn

Tên đơn giản không phải lúc nào cũng chỉ đến lớp mong đợi. Một lớp thành viên hoặc một kiểu cục bộ có thể **shadow** tên được cung cấp từ một import. Ví dụ minh họa phạm vi:

~~~java
class Outer {
    static class Item {
    }

    void use() {
        Item value = new Item();
        System.out.println(value.getClass().getSimpleName());
    }
}
~~~

`Item` trong `use()` chỉ đến `Outer.Item`. Nếu cũng có kiểu `some.library.Item` trên classpath, sự tồn tại của kiểu đó không làm `Item` ở phương thức `use()` đổi nghĩa. Để sử dụng kiểu từ thư viện trong một phạm vi cho phép, có thể viết tên đủ điều kiện `some.library.Item` (giả định đó là một lớp tồn tại và truy cập được).

**Lưu ý:** ví dụ `Outer` là đoạn minh họa cho cách tên được tìm trong phạm vi của một lớp; nó không tự chạy vì không có `main`. Những quy tắc chi tiết về scope, shadowing và obscuring được nêu trong Java Language Specification, chương 6. Khi có xung đột khó hiểu, đọc khai báo `package`, `import`, lớp bao quanh và kiểu cục bộ trước khi suy đoán compiler “chọn ngẫu nhiên”.

## 8. Lớp lồng nhau: canonical name khác binary name

Lớp cấp cao nhất `school.Student` có tên trong mã nguồn là `school.Student`. Nhưng lớp thành viên được viết bằng dấu chấm trong Java có thể có **binary name** dùng dấu `$` trong tệp `.class` và API phản chiếu.

Ví dụ hoàn chỉnh: tạo **`src/demo/TypeNameDemo.java`** trong một thư mục ví dụ độc lập.

~~~java
package demo;

public class TypeNameDemo {
    static class Nested {
    }

    public static void main(String[] args) {
        Class<?> type = Nested.class;

        System.out.println(type.getSimpleName());
        System.out.println(type.getCanonicalName());
        System.out.println(type.getName());
    }
}
~~~

Tại thư mục cha chứa `src`, chạy:

~~~bash
javac -d out src/demo/TypeNameDemo.java
java -cp out demo.TypeNameDemo
~~~

Stdout:

~~~text
Nested
demo.TypeNameDemo.Nested
demo.TypeNameDemo$Nested
~~~

Ba API trả lời ba câu hỏi khác nhau:

| API | Với `TypeNameDemo.Nested` | Ý nghĩa |
| --- | --- | --- |
| `getSimpleName()` | `Nested` | Tên đơn giản của lớp |
| `getCanonicalName()` | `demo.TypeNameDemo.Nested` | Tên canonical, có thể dùng khi viết tên kiểu trong Java ở ngữ cảnh hợp lệ |
| `getName()` | `demo.TypeNameDemo$Nested` | Binary name mà Java runtime dùng cho lớp thành viên |

Không nên chép `demo.TypeNameDemo$Nested` vào mã nguồn để thay thế cách viết kiểu thông thường `demo.TypeNameDemo.Nested`. Với lớp cục bộ, lớp vô danh và một số kiểu đặc biệt, `getCanonicalName()` còn có thể trả về `null`, vì không phải mọi kiểu runtime đều có canonical name.

Dấu `$` trong kết quả trên là quy ước binary naming của lớp thành viên, **không phải dấu phân cách package**. Đường dẫn `out/demo/TypeNameDemo$Nested.class` cũng có thể xuất hiện sau khi biên dịch.

## 9. Quy trình xử lý khi IDE hoặc javac báo lỗi tên kiểu

Khi gặp `cannot find symbol`, `reference to ... is ambiguous`, hoặc lớp có tên đúng nhưng import không chạy, nên kiểm tra theo thứ tự hợp lý:

1. **Xác định lớp mong muốn:** ghi tên đủ điều kiện của kiểu, chẳng hạn `school.Student`; đừng chỉ dựa vào tên ngắn.
2. **Kiểm tra package trong tệp khai báo:** `package school;` khác `package company;`. Đảm bảo tệp đã được đưa vào biên dịch hoặc thư viện có trên classpath/module path.
3. **Kiểm tra quyền truy cập:** kiểu cấp cao nhất từ package khác thường phải `public`; với named modules, package còn phải được export và module sử dụng phải đọc được module chứa kiểu.
4. **Kiểm tra import ở đúng tệp:** `import school.Student;` phải nằm sau `package` và trước khai báo lớp, trong tệp sử dụng; import ở tệp bên cạnh không có tác dụng thay.
5. **Kiểm tra xung đột:** có hai single-type import tên `Student` không? Có import `*` từ hai package đều có `Student` không? Có lớp thành viên hoặc kiểu cục bộ cùng tên không?
6. **Thử tên đủ điều kiện:** viết `school.Student` ngay tại vị trí sử dụng để kiểm chứng kiểu cần tham chiếu. Nếu vẫn lỗi, vấn đề có thể là thiếu dependency, khai báo tên sai hoặc quyền truy cập.
7. **Kiểm tra lệnh chạy:** sau khi biên dịch có package, dùng `java -cp out app.NameConflictDemo` thay vì chỉ tên đơn giản.

Phân biệt nguyên nhân: **tên không tìm thấy** thường do thiếu định nghĩa/import/đường tìm kiểu; **tên mơ hồ** do nhiều kiểu đủ điều kiện cùng có thể ứng với tên ngắn; **không truy cập được** do modifier hoặc ranh giới module/package. Viết tên đủ điều kiện có thể giải quyết tính mơ hồ của tên, nhưng **không vượt qua** quy tắc truy cập hay tự cung cấp dependency còn thiếu.

## 10. Quy tắc đặt tên và những lỗi phổ biến

| Thói quen hoặc hiểu lầm | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| Đặt mọi lớp vào unnamed package | Khó quản lý dự án lớn, không import kiểu từ unnamed package vào một named package | Khai báo package rõ ràng cho mã dự án |
| Dùng cùng tên lớp `Util`, `Manager` ở nhiều nơi không có chủ đích | Người đọc khó phân biệt ý nghĩa; import dễ xung đột | Đặt tên theo vai trò, package rõ ràng |
| Nghĩ `import x.*` bao gồm mọi package con | Không tìm được các lớp trong `x.y` | Import đúng package/type cần dùng |
| Viết hai single-type import khác nhau có chung simple name | Lỗi biên dịch ngay trên import | Import một kiểu, dùng fully qualified name cho kiểu khác |
| Nghĩ `import` tạo instance hoặc nạp code ngay | Nhầm cú pháp tổ chức tên với tạo đối tượng/runtime | `new` tạo instance; `import` chỉ hỗ trợ tham chiếu tên |
| Nghĩ dùng fully qualified name bỏ qua `private`/module exports | Lỗi truy cập dù đường dẫn lớp chính xác | Kiểm tra modifier và cấu hình module |
| Chạy main class thuộc package bằng tên ngắn tùy ý | JVM có thể báo không tìm thấy main class | Dùng tên đầy đủ cùng classpath phù hợp |
| Dùng kết quả `Class.getName()` của nested class như cú pháp Java nguồn | Nhầm binary name `Outer$Inner` với canonical name `Outer.Inner` | Dùng tên kiểu phù hợp trong Java; phân biệt API phản chiếu |

Quy ước hữu ích: tên package viết chữ thường, thường theo tên miền đảo ngược như `com.example.school`; tên lớp dùng PascalCase như `BankAccount`, `StudentRepository`. Quy ước giúp giảm xung đột nhưng **không thay đổi** các quy tắc ngôn ngữ về tên đơn giản và tên đủ điều kiện.

Một kiểu có thể được biết dưới nhiều dạng tên trong công cụ Java. Tuy vậy, trong mã nguồn thông thường, hãy chọn tên ngắn khi nó **rõ nghĩa và không mơ hồ**, dùng tên đủ điều kiện khi thật sự cần phân biệt hai lớp.

## 11. Tự luyện tập

**Câu 1.** Trong `package shop.inventory; public class Product {}`, đâu là tên đơn giản, đâu là tên đủ điều kiện?

**Câu 2.** Có `a.User` và `b.User`. Trong cùng tệp `Main.java`, hãy viết một cách hợp lệ để tạo mỗi lớp một đối tượng, không cần import gì.

**Câu 3.** Vì sao hai dòng `import a.User;` và `import b.User;` trong cùng một tệp gây lỗi ngay cả khi `User` chưa được sử dụng?

**Câu 4.** `import java.util.*;` có khiến `ExecutorService` trong `java.util.concurrent` dùng được trực tiếp không? Giải thích.

**Câu 5.** Khi `Class.getName()` của lớp thành viên `app.Outer.Inner` trả về `app.Outer$Inner`, tên nào nên dùng để chỉ kiểu đó trong một khai báo biến Java thông thường?

**Đáp án ngắn:**

1. `Product` là tên đơn giản; `shop.inventory.Product` là tên đủ điều kiện.
2. Viết `a.User first = new a.User();` và `b.User second = new b.User();`, giả định hai kiểu có constructor không tham số truy cập được.
3. Hai single-type import cố đưa cùng tên đơn giản `User` từ hai kiểu khác nhau vào một compilation unit.
4. Không; package con không được import theo kiểu đệ quy. Cần `import java.util.concurrent.ExecutorService;` hoặc tên đủ điều kiện.
5. Dùng `app.Outer.Inner` trong mã nguồn, miễn lớp và thành viên đó truy cập được; `$` thuộc binary name.

## 12. Tài liệu đối chiếu

- [Java Language Specification 17, Chương 6 — Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html): tên, phạm vi, shadowing, qualified/canonical/binary names.
- [Java Language Specification 17, Chương 7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): package, compilation unit, import và phạm vi truy cập.

**Ghi nhớ:** *Tên đơn giản* giúp mã ngắn gọn; *tên đủ điều kiện* làm rõ kiểu được nhắc đến. `package` tạo không gian tên, `import` đưa một tên thích hợp vào phạm vi của tệp nguồn, và khi trùng tên lớp, Java yêu cầu bạn chỉ ra một kiểu không mơ hồ.
