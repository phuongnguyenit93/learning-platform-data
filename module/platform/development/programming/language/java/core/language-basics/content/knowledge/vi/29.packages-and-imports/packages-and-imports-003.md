# Tên đơn giản và tên đầy đủ của lớp trong Java

## 1. Tên đơn giản (*simple name*) và tên đầy đủ (*fully qualified name*)

Java tổ chức các lớp, interface, enum, record và những kiểu khác trong các **package**. Với một kiểu top-level, có hai cách gọi tên phổ biến:

- **Tên đơn giản** (*simple name*): tên khai báo ngay sau `class`, `interface`, `enum`, hoặc `record`; ví dụ `ArrayList`, `String`, `Student`.
- **Tên đầy đủ** (*fully qualified name*, trong ngữ cảnh bài này là tên có package): tên package cộng dấu chấm và tên kiểu; ví dụ `java.util.ArrayList`, `java.lang.String`, `com.example.model.Student`.

```java
// Tên đơn giản:
ArrayList<String> names;

// Tên đầy đủ:
java.util.ArrayList<String> others;
```

Hai cách có thể chỉ **cùng một kiểu**, nếu tên đơn giản `ArrayList` được Java phân giải đúng thành `java.util.ArrayList` (thường nhờ `import`).

Một **package** không phải đối tượng và cũng không phải nơi giữ trạng thái runtime; nó tạo không gian tên để tổ chức các kiểu và tránh va chạm tên. Theo quy ước Java, tên package thường là chữ thường, chẳng hạn `com.example.app`, còn tên lớp là PascalCase như `OrderService`.

**Phân biệt:** tên đầy đủ theo dấu chấm trong mã nguồn Java khác tên tệp `.java` hoặc tên lớp dạng nhị phân (*binary name*) cho kiểu lồng nhau. Với `java.util.Map.Entry`, tên canonical trong Java là `java.util.Map.Entry`, trong khi `Class.getName()` của kiểu này trả `java.util.Map$Entry`.

## 2. Package, khai báo lớp và vị trí tệp

Ví dụ:

```java
package com.example.model;

public class Student {
    private final String name;

    public Student(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

Đoạn trên là nội dung đầy đủ của **`Student.java`**. Tên đơn giản của lớp là `Student`; tên đầy đủ là `com.example.model.Student`. Trong một source file thông thường, `package` (nếu có) đứng đầu sau các nhận xét, trước các `import` và khai báo kiểu top-level.

Quy tắc cơ bản:

- Một kiểu top-level `public class Student` phải được khai báo trong source file tên **`Student.java`**.
- `package com.example.model;` xác định package theo **khai báo trong mã nguồn**, không tự được quyết định bởi tên thư mục.
- Bố cục thư mục tương ứng với package, như `src/com/example/model/Student.java`, là quy ước và cách tổ chức thông thường giúp công cụ biên dịch, build và classpath tìm thấy lớp đúng vị trí.
- Biên dịch bằng `javac -d out ...` đặt file lớp vào cấu trúc thư mục theo package, chẳng hạn `out/com/example/model/Student.class`.
- Chạy một lớp có `main` trong package bằng **tên đầy đủ của lớp** như `java -cp out com.example.app.Main`; `java -cp out Main` sẽ không tìm đúng tên lớp đó.

Không nên nhầm *tên đơn giản* của lớp `Student` với *tên biến* `student` khi tạo `Student student = new Student("An");`.

## 3. `import` cho phép viết tên đơn giản

Nếu tệp nguồn nằm ở package khác với lớp muốn dùng, ta thường thêm một hoặc vài khai báo `import`:

```java
package com.example.app;

import java.util.ArrayList;
import java.util.List;

public class Demo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        System.out.println(words); // [Java]
    }
}
```

Trong ví dụ này, `List` là tên đơn giản đại diện cho `java.util.List`; `ArrayList` đại diện cho `java.util.ArrayList`.

**`import` không tạo đối tượng, không sao chép mã và không nạp lớp theo nghĩa chạy chương trình.** Nó là khai báo giúp trình biên dịch nhận diện tên ngắn tại nơi có hiệu lực. Không cần `import` nếu viết tên đầy đủ ngay trong mã:

```java
java.util.List<String> words = new java.util.ArrayList<>();
words.add("Java");
```

Cả hai cách viết đều dùng đúng các kiểu từ `java.util`.

Các dạng hay gặp:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `import java.util.List;` | Import một kiểu cụ thể; cho phép dùng `List` như tên đơn giản khi không bị xung đột |
| `import java.util.*;` | Import theo yêu cầu các kiểu truy cập được trực tiếp thuộc package `java.util` |
| `import static java.lang.Math.max;` | Cho phép gọi thành viên static `max` bằng tên ngắn |
| `import static java.lang.Math.*;` | Static import theo yêu cầu các thành viên static truy cập được của `Math` |
| `java.sql.Date` | Dùng tên đầy đủ tại vị trí cần; không phụ thuộc import `Date` của package nào |

`import java.util.*;` **không import các package con** của `java.util`, chẳng hạn `java.util.concurrent`. Ký hiệu `*` cũng không có nghĩa tự import toàn bộ thư viện Java.

Các kiểu trong `java.lang` như `String`, `Object`, `System`, `Math` được import **ngầm định theo yêu cầu**; các kiểu thuộc **cùng package** cũng có thể được gọi theo tên đơn giản khi không có xung đột. Vì vậy không cần viết `import java.lang.String;` trong chương trình thông thường.

## 4. Khi tên đơn giản không đủ xác định kiểu

`java.util.Date` và `java.sql.Date` có simple name `Date` giống nhau nhưng là hai kiểu khác nhau. Trong một compilation unit, có thể import một kiểu và viết tên đầy đủ cho kiểu còn lại:

~~~java
import java.util.Date;

class Dates {
    Date general = new Date(0L);
    java.sql.Date database = new java.sql.Date(0L);
}
~~~

Hai **single-type imports** cho hai kiểu khác nhau cùng simple name gây lỗi; hai wildcard imports có thể khiến tên ngắn mơ hồ ở nơi dùng. Bài về xung đột import phân tích sâu các trường hợp này. Ở đây chỉ cần nhớ tên đầy đủ giúp xác định kiểu chính xác.

## 5. Quy tắc tra cứu tên: vài tình huống quan trọng

Trình biên dịch phân giải một tên kiểu đơn giản dựa trên **ngữ cảnh cú pháp và các khai báo/import đang có**, không đơn giản tìm một lớp ngẫu nhiên trùng tên trong toàn bộ classpath.

Các tình huống thường gặp:

1. **Kiểu đã được khai báo hoặc nằm trong phạm vi phù hợp** có thể được nhắc bằng tên đơn giản theo quy tắc scope và khả năng truy cập.
2. **Kiểu trong cùng package** có thể được dùng không cần import.
3. **Single-type import** như `import java.util.List;` cung cấp tên ngắn cho một kiểu cụ thể; import trùng tên có thể gây lỗi biên dịch.
4. **On-demand import** như `import java.util.*;` cung cấp các kiểu khi cần; nếu có nhiều ứng viên với cùng tên đơn giản, có thể phải chỉ rõ tên đầy đủ.
5. **`java.lang`** được import ngầm; tuy nhiên vẫn có thể có những tên trùng với kiểu do chương trình tự khai báo trong ngữ cảnh thích hợp.

Đây là cách đọc thực dụng, **không thay thế toàn bộ thứ tự tra cứu tên** trong Java Language Specification. Khi một tên đơn giản đang trỏ tới kiểu không mong muốn, hãy kiểm tra package hiện tại, các khai báo cùng scope, import cụ thể và wildcard imports; sau đó dùng tên đầy đủ để xác nhận ý định.

**Phân biệt quyền truy cập với việc import:** một lớp `package-private` không tự trở thành truy cập được từ package khác chỉ vì có `import`. Import không vượt qua giới hạn `public`, `protected`, package access hay `private`.

## 6. Ví dụ Java 17+ chạy độc lập, chứng minh cả hai cách gọi

Tạo thư mục và tệp **`src/study/NameResolutionDemo.java`** theo nội dung:

```java
package study;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Map;
import static java.lang.Math.max;
import static java.lang.Math.PI;

public class NameResolutionDemo {
    public static void main(String[] args) {
        // List và ArrayList là tên đơn giản nhờ import.
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Binh");
        System.out.println("Names: " + names);

        // java.util.ArrayList là tên đầy đủ cho cùng kiểu.
        java.util.List<String> other = new java.util.ArrayList<>();
        other.add("Java");
        System.out.println("Other: " + other);

        // Hai lớp Date khác package, tránh trùng tên đơn giản.
        Date utilDate = new Date(0L);
        java.sql.Date sqlDate = new java.sql.Date(0L);
        System.out.println("Util Date class: " + utilDate.getClass().getName());
        System.out.println("SQL Date class: " + sqlDate.getClass().getName());

        // Kiểu lồng nhau: Map.Entry có tên canonical nhiều thành phần.
        Map.Entry<String, Integer> entry = Map.entry("apple", 2);
        System.out.println("Entry: " + entry.getKey() + "=" + entry.getValue());

        // java.lang tự có import ngầm; max và PI từ static import.
        System.out.println("Max: " + max(3, 5));
        System.out.println("PI > 3: " + (PI > 3.0));
        System.out.println("Simple class: " + names.getClass().getSimpleName());
        System.out.println("Full class: " + names.getClass().getName());
    }
}
```

**Biên dịch và chạy** (JDK 17+, đứng ở thư mục gốc của ví dụ, có tệp `src/study/NameResolutionDemo.java`):

**Tạo sẵn thư mục gốc `out` trước lệnh `javac -d out` nếu chưa tồn tại**: Bash/Linux/macOS chạy `mkdir -p out`; Windows PowerShell chạy `New-Item -ItemType Directory -Force out | Out-Null`. `javac` có thể tạo các thư mục *bên trong* `out` theo package nhưng không tự tạo thư mục đích `out` còn thiếu.

```bash
javac -encoding UTF-8 -d out src/study/NameResolutionDemo.java
java -cp out study.NameResolutionDemo
```

Hai dòng lệnh giống nhau trong PowerShell, CMD, bash hoặc zsh. Thư mục `out` là nơi `javac` tạo cây `study/NameResolutionDemo.class`; có thể để trình biên dịch tự tạo cấu trúc thư mục bên trong `out`. Dùng `study.NameResolutionDemo` vì lớp `NameResolutionDemo` nằm trong package `study`.

**Stdout chính xác** (khi biên dịch thành công, `javac` không in gì):

```text
Names: [An, Binh]
Other: [Java]
Util Date class: java.util.Date
SQL Date class: java.sql.Date
Entry: apple=2
Max: 5
PI > 3: true
Simple class: ArrayList
Full class: java.util.ArrayList
```

Các kết quả `getClass().getSimpleName()` và `getClass().getName()` ở đây đọc từ đối tượng `ArrayList` thực tế. Đừng dùng `getSimpleName()` làm cơ chế xác minh duy nhất khi có hai lớp khác package cùng tên, vì thông tin package bị lược bỏ.

### Tên của kiểu lồng nhau và tên nhị phân

Ví dụ `Map.Entry` là một interface lồng nhau có tên đơn giản `Entry`; trong mã Java, có thể viết `java.util.Map.Entry` mà không phải trực tiếp nhắc tới ký tự `$`.

```java
System.out.println(java.util.Map.Entry.class.getCanonicalName());
// java.util.Map.Entry

System.out.println(java.util.Map.Entry.class.getName());
// java.util.Map$Entry
```

Đoạn này minh họa trong phương thức; chương trình hoàn chỉnh ở trên. `getCanonicalName()` và `getName()` khác nhau khi xử lý tên một số kiểu lồng nhau. Nếu dùng các API reflection như `Class.forName`, cần hiểu định dạng tên **nhị phân** mà API yêu cầu.

## 7. Không nên nhầm `import` với `classpath` hoặc module

`import` chỉ giải quyết cách **viết tên kiểu** trong file source. Muốn biên dịch/chạy được, trình biên dịch và JVM còn phải tìm thấy định nghĩa lớp trên classpath hoặc module path tương ứng.

- **`package`** xác định không gian tên của kiểu; chỉ khai báo `package study;` không tự cài đặt thư viện hoặc tải một `.jar` bên ngoài.
- **`import`** giúp viết tên đơn giản; không chỉ định nơi tìm `.class`, không thêm thư viện vào classpath.
- **`classpath`**, ví dụ `javac -cp libs/example.jar ...`, chỉ vị trí phụ thuộc khi biên dịch. `java -cp ...` chỉ vị trí lớp khi chạy.
- Trong ứng dụng dùng **Java Platform Module System** (JPMS), khả năng sử dụng kiểu còn chịu quy tắc module như `requires` và `exports`; import không thay thế khai báo module.
- Các kiểu trong **unnamed package** (không khai báo `package`) không thể được mã trong named package import theo cách thông thường; dự án thực tế nên dùng package có tên.

Nếu báo lỗi `cannot find symbol`, `package ... does not exist` hoặc `ClassNotFoundException`, hãy phân biệt vấn đề **phân giải tên trong mã** với vấn đề **thiếu lớp/thư viện khi biên dịch hoặc chạy**.

## 8. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `List` và `java.util.List` luôn là hai kiểu khác nhau | Nếu `List` được phân giải đến `java.util.List`, chúng là cùng một kiểu |
| Phải import để dùng một lớp ngoài package | Có thể viết tên đầy đủ mà không import |
| `import java.util.*;` tự import luôn `java.util.concurrent.*` | Wildcard import chỉ áp dụng cho một package/kiểu theo quy tắc cụ thể, không mở rộng vào subpackage |
| Hai lớp tên `Date` của hai package tự động tương đương | `java.util.Date` và `java.sql.Date` là hai lớp khác nhau |
| Import giúp dùng lớp `private` hoặc package-private từ bất cứ đâu | Quy tắc truy cập vẫn có hiệu lực |
| Đã import nghĩa là JVM chắc chắn tìm thấy lớp lúc chạy | Dependency phải có trên classpath/module path tương ứng |
| `Class.getName()` luôn bằng tên canonical viết trong Java | Kiểu lồng nhau có thể dùng `$` trong binary name |
| Chạy lớp trong package bằng tên đơn giản sau `java` | Dùng tên đầy đủ như `java -cp out study.NameResolutionDemo` |

**Ghi nhớ:** tên đơn giản giúp mã gọn; tên đầy đủ giúp xác định chính xác một kiểu. `package` tổ chức không gian tên, `import` hỗ trợ phân giải tên ngắn, còn classpath/module path quyết định nơi tìm định nghĩa lớp.