# Module import declarations và phạm vi tên được nhập

**Module import declaration** cho phép một file nguồn Java dùng các kiểu công khai do một module xuất ra mà không phải liệt kê từng package. Từ Java 25, cú pháp **`import module M;`** đã trở thành tính năng chính thức của ngôn ngữ (JEP 511); trong **Java 27** nó tiếp tục được quy định tại *Java Language Specification (JLS) §7.5.5*.

Ví dụ, một file sử dụng `List`, `Path`, `LocalDate` và `Stream` từ nhiều package của module `java.base` có thể bắt đầu bằng một dòng:

~~~java
import module java.base;
~~~

Điểm quan trọng là **module import chỉ đưa các tên kiểu có thể truy cập vào phạm vi của compilation unit**. Nó không tự mở package nội bộ, không thêm quan hệ `requires` vào descriptor của named module, không nhập các phương thức static, và không làm cho cùng một `import` có tác dụng đối với những file Java khác.

Bài thuộc chương **Module và đóng gói thư viện** của module **Java 27 và các kiến thức liên quan**. Nội dung chỉ dùng quy tắc và cú pháp Java hiện hành, không dựa vào trạng thái preview của các bản Java cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Viết và đọc đúng `import module M;` trong Java 27.
- Phân biệt **single-module-import**, **single-type-import**, **type-import-on-demand** và **static import**.
- Giải thích chính xác những package/kiểu được import khi module có `exports`, `exports ... to` và `requires transitive`.
- Phân biệt **import tên kiểu**, **module readability** và **quyền truy cập kiểu**.
- Xác định phạm vi của tên được import trong ordinary/compact/modular compilation unit.
- Giải quyết việc trùng simple name bằng import tường minh hoặc fully qualified name.
- Hiểu quy tắc shadowing giữa `import module`, `import java.util.*`, `import java.util.List` và `java.lang`.
- Biết khi nào dùng module import giúp mã rõ ràng và khi nào nên giữ các import chi tiết để tránh mơ hồ.

## 2. Phân biệt module, package và kiểu dữ liệu

### 2.1. Module nhóm các package

Trong Java Platform Module System (JPMS):

- **Module** có tên như `java.base`, `java.sql`, `java.xml` hoặc `com.example.reports`.
- **Package** nhóm các kiểu, chẳng hạn `java.util`, `java.util.stream`, `java.nio.file`.
- **Kiểu (type)** là class hoặc interface (kể cả record, enum và annotation interface theo hình thức khai báo tương ứng), chẳng hạn `java.util.List` hay `java.nio.file.Path`.
- Descriptor `module-info.java` mô tả quan hệ đọc module bằng `requires` và API công khai qua `exports`.

Ví dụ:

~~~text
Module java.base
├── package java.lang
│   ├── String
│   └── Math
├── package java.util
│   ├── List
│   └── Map
├── package java.util.stream
│   └── Stream
├── package java.nio.file
│   └── Path
└── package java.time
    └── LocalDate
~~~

Đây là sơ đồ giản lược, không phải danh sách tất cả package và kiểu của `java.base`.

### 2.2. Import kiểu không giống import module ở JPMS

Cụm “import module” đôi khi gây hiểu nhầm rằng nó thay thế khai báo dependency của module. Thực chất có hai lớp trách nhiệm riêng:

1. **JPMS** xác định module nào được đọc và những package nào được phép truy cập.
2. **Import declaration** cho phép viết simple name như `List` thay vì `java.util.List` trong phạm vi file nguồn.

Với một named module, `requires java.sql;` trong `module-info.java` là khai báo quan hệ dependency. Còn `import module java.sql;` ở file dùng JDBC là cú pháp giúp các tên kiểu hiện diện trong file đó. Hai câu lệnh có mục đích khác nhau và không thay thế cho nhau.

## 3. Tổng quan các loại import trong Java

JLS §7.5 phân biệt năm dạng import:

| Dạng | Cú pháp | Đưa gì vào phạm vi? |
|---|---|---|
| Single-type-import | `import java.util.List;` | Một kiểu cụ thể |
| Type-import-on-demand | `import java.util.*;` | Các kiểu có thể truy cập của **một** package (hoặc một type) theo nhu cầu |
| Single-static-import | `import static java.lang.Math.PI;` | Thành viên static được chỉ định |
| Static-import-on-demand | `import static java.lang.Math.*;` | Những thành viên static có thể truy cập theo nhu cầu |
| Single-module-import | `import module java.base;` | Các kiểu top-level public từ các package được module export và các module đọc được thông qua nó |

Dấu `*` trong `import java.util.*;` **không có nghĩa** là nhập mọi subpackage. Ví dụ, câu lệnh đó không tự nhập `java.util.stream.Stream`, bởi `java.util.stream` là package riêng.

Ngược lại, `import module java.base;` có thể làm sẵn simple name từ **nhiều package khác nhau** mà `java.base` export.

### 3.1. Ví dụ so sánh trực tiếp

Không dùng module import:

~~~java
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Stream;

public class DetailedImports {
    static void show() {
        List<String> names = List.of("An", "Bình");
        Stream<String> stream = names.stream();

        System.out.println(stream.count());
        System.out.println(Path.of("notes.txt"));
        System.out.println(LocalDate.of(2026, 11, 27));
    }
}
~~~

Dùng module import:

~~~java
import module java.base;

public class ModuleImports {
    static void show() {
        List<String> names = List.of("An", "Bình");
        Stream<String> stream = names.stream();

        System.out.println(stream.count());
        System.out.println(Path.of("notes.txt"));
        System.out.println(LocalDate.of(2026, 11, 27));
    }
}
~~~

Hai ví dụ thể hiện cùng loại API được sử dụng; bản thứ hai không phải vì Java tự bổ sung `requires` hay tải lại class, mà vì các simple name trong file được tìm qua module import.

## 4. Cú pháp và ý nghĩa của import module M

### 4.1. Cú pháp chính thức

Theo JLS §7.5.5, cú pháp là:

~~~java
import module java.base;
import module java.sql;
~~~

Cấu trúc tổng quát:

~~~text
import module ModuleName;
~~~

`ModuleName` là **tên module**, không phải tên package, không phải tên class, không phải tên file JAR.

Không hợp lệ:

~~~java
// Sai: import module phải nêu module name, không phải package.
// import module java.util;

// Sai: cú pháp này không có wildcard.
// import module java.base.*;

// Sai: module import không phải static import.
// import static module java.base;
~~~

`java.util` ở ví dụ là package nằm trong module `java.base`. Nếu chỉ muốn dùng các kiểu của `java.util` thì dùng `import java.util.*;` hoặc các single-type-import cụ thể.

### 4.2. Import theo nhu cầu (on demand)

Module import không bắt buộc chương trình thực sự sử dụng mọi kiểu do module công bố. Các tên kiểu được xem xét khi cần phân giải tên xuất hiện trong file.

~~~java
import module java.base;

class Names {
    List<String> values = List.of("A", "B");
    Path file = Path.of("data.txt");
}
~~~

Trong ví dụ này, chỉ `List` và `Path` được dùng. Không có chuyện compiler tạo biến hay object cho toàn bộ các class của `java.base`.

### 4.3. Chỉ nhập các kiểu top-level public có thể truy cập

Module import không tự nhập mọi thành phần của module:

- **Có thể nhập:** các **public top-level classes và interfaces** trong những package được export cho module hiện tại.
- **Không nhập:** package-private top-level types từ package khác.
- **Không nhập:** kiểu thuộc package nội bộ không được export thích hợp.
- **Không trực tiếp nhập:** static methods/fields và member/nested types chỉ vì chúng là thành viên của một class đã được nhập.
- **Không nhập:** tên package như một kiểu độc lập.

Ví dụ:

~~~java
import module java.base;

class TypeAndMember {
    Map<String, Integer> map = Map.of("A", 1);

    // Entry là nested interface của Map:
    Map.Entry<String, Integer> item = Map.entry("B", 2);

    // Không được import trực tiếp tên 'Entry' chỉ vì import module:
    // Entry<String, Integer> bad = Map.entry("C", 3);
}
~~~

Muốn dùng tên ngắn `Entry`, có thể viết `import java.util.Map.Entry;` nếu thích hợp. Module import cho phép dùng `Map`, không tự biến mọi nested type thành simple name độc lập.

Tương tự:

~~~java
import module java.base;

class StaticMembers {
    double area(double r) {
        return Math.PI * r * r; // Math được nhìn thấy qua java.lang
    }

    // Không thể gọi PI không có qualifier nếu không import static:
    // double invalid = PI;
}
~~~

Nếu muốn viết `PI` trực tiếp, dùng `import static java.lang.Math.PI;`; module import không thay thế static import.

## 5. Tập package mà một module import mang lại

### 5.1. Hai nhóm theo JLS §7.5.5

Giả sử file chứa:

~~~java
import module M;
~~~

Câu lệnh này thực hiện on-demand import của public top-level types từ:

1. **Các package mà module `M` export tới module hiện tại.**
2. **Các package được export bởi những module mà module hiện tại đọc được nhờ việc đọc `M`**, tức chuỗi phụ thuộc `requires transitive` tương ứng.

Điều này giúp mã có thể sử dụng API của `M` và các kiểu liên quan mà `M` công bố qua dependency transitive.

**Không phải mọi module mà `M` có `requires` đều được kéo vào import.** Quan hệ `requires` thông thường và `requires transitive` khác nhau về readability cho các module phụ thuộc.

### 5.2. Ví dụ trên một graph module giả định

Giả sử các module có descriptor:

~~~java
// module M0
module M0 {
    requires M1;
}
~~~

~~~java
// module M1
module M1 {
    exports p1;
    exports p2 to M0;
    exports p3 to M3;

    requires transitive M4;
    requires M5;
}
~~~

~~~java
// module M4
module M4 {
    exports p10;
}
~~~

~~~java
// module M5
module M5 {
    exports p11;
}
~~~

Trong file thuộc `M0`:

~~~java
package q;

import module M1;

class Example {
    // Có thể dùng simple names của các public top-level types
    // trong p1, p2 và p10 nếu chúng không bị shadow/ambiguous.
}
~~~

Phân tích:

| Package | Có được module import đưa vào phạm vi? | Vì sao? |
|---|---|---|
| `p1` | Có | `M1` export công khai |
| `p2` | Có | `M1` export được chỉ định tới `M0` |
| `p3` | Không | Chỉ export tới `M3`, không phải `M0` |
| `p10` | Có | `M1 requires transitive M4`; `M4` export `p10` |
| `p11` | Không | `M1 requires M5` thông thường, không tạo readability transitive cho `M0` |

Ví dụ này minh họa trực tiếp quy tắc JLS §7.5.5; các module `M0` đến `M5` chỉ là ký hiệu mô hình, không phải các module Java SE có sẵn.

### 5.3. Ví dụ thật: java.sql kéo theo logging và XML

Theo descriptor hiện hành của `java.sql`, module này export `java.sql` và `javax.sql`, đồng thời `requires transitive` tới các module như `java.logging` và `java.xml`.

Vì vậy, khi module hiện tại đọc `java.sql`, câu lệnh:

~~~java
import module java.sql;
~~~

có thể làm sẵn những simple name như:

- `Connection` và `DriverManager` từ `java.sql`.
- `Logger` từ `java.util.logging`, thuộc `java.logging`.
- `DocumentBuilderFactory` từ `javax.xml.parsers`, thuộc `java.xml`.

Ví dụ:

~~~java
import module java.sql;

class SqlTypes {
    Connection connection;
    Logger logger;
    DocumentBuilderFactory parserFactory;
}
~~~

Các trường trên chỉ minh họa khả năng phân giải tên; chúng không tự mở kết nối database hoặc khởi tạo parser. Trong **named module**, vẫn cần đảm bảo quan hệ readability (ví dụ khai báo `requires java.sql;`).

### 5.4. Module java.se: không phải import mọi thứ của JDK

`java.se` là một **aggregator module**, gom nhiều module Java SE qua các quan hệ transitive; một module aggregator có thể không tự export package nhưng vẫn làm `import module java.se;` đưa tên kiểu của các module liên quan vào phạm vi.

Điều đó **không** tương đương “nhập toàn bộ class trong JDK”, bởi JDK có thêm module/tool/API không thuộc tập module mà `java.se` làm cho readable. Nó cũng tăng nguy cơ trùng simple name, nên thường không cần thiết cho một file chỉ dùng vài package.

Không nên dựa vào các thay đổi riêng còn ở trạng thái preview khi giải thích tính năng ổn định này. Với code sản phẩm, chọn module trực tiếp nhỏ và rõ ràng thường dễ bảo trì hơn.

## 6. Điều kiện tiên quyết: module phải readable

### 6.1. Import không tạo readability

Quy tắc then chốt trong JLS §7.5.5:

**Sẽ có lỗi biên dịch nếu module được nêu trong single-module-import không được module hiện tại đọc (not readable).**

Trong named module:

~~~java
// module-info.java
module com.example.reports {
    requires java.sql;
}
~~~

Một file nguồn thuộc `com.example.reports` có thể viết:

~~~java
package com.example.reports;

import module java.sql;

public class Report {
    DriverManager managerReference; // Chỉ minh họa tên kiểu
}
~~~

`DriverManager` vốn là class với các phương thức static; không có lý do nghiệp vụ để khai báo biến kiểu đó ở ví dụ thực tế. Có thể viết `DriverManager.class.getModule()` để minh họa tên kiểu mà không cần tạo đối tượng.

Nếu bỏ `requires java.sql;` mà module hiện tại không đọc `java.sql` bằng quan hệ nào khác, `import module java.sql;` **không** thay thế được `requires` và có thể dẫn đến compile-time error.

### 6.2. java.base là trường hợp đặc biệt

Mọi module đều đọc `java.base` theo quy tắc JPMS, và `java.lang` tự động có sẵn qua implicit import. Vì vậy một file nguồn trong named module có thể dùng:

~~~java
import module java.base;
~~~

mà không cần viết `requires java.base;` trong module descriptor.

Điều này không mở quyền truy cập tới các internal API thuộc `java.base` không được export; module readability và accessibility vẫn phải thỏa mãn.

### 6.3. Module đọc được nhờ requires transitive cũng có thể import

Giả sử `M0` có `requires M1;` và `M1` có `requires transitive M4;`. Khi module graph được giải quyết, `M0` đọc `M4` nhờ quan hệ transitive.

Vì vậy `M0` có thể viết `import module M4;` nếu module `M4` readable tại thời điểm biên dịch, dù `module-info.java` của `M0` không chứa `requires M4;` trực tiếp. Quy tắc hợp lệ phụ thuộc **readability thực tế**, không chỉ việc tên module xuất hiện trong `requires` trực tiếp.

### 6.4. File không thuộc named module vẫn có thể dùng

Một chương trình trên classpath thuộc unnamed module có thể dùng module import cho các module hệ thống được giải quyết và đọc được:

~~~java
import module java.base;

public class SimpleApp {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3);
        System.out.println(numbers);
    }
}
~~~

Điều này không yêu cầu tác giả tự tạo `module-info.java`. Nhưng với **module tùy biến không tự động được giải quyết**, cần cấu hình module path và khả năng quan sát/đọc phù hợp. Đừng suy ra chỉ vì classpath có một JAR thì `import module tên.module;` luôn biên dịch được.

## 7. Phạm vi tên được import: compilation unit nào nhận tác dụng?

### 7.1. Chỉ trong compilation unit chứa import

Theo JLS §7.5 và §6.3, tên được import chỉ nằm trong phạm vi **compilation unit** chứa câu lệnh import.

~~~text
src/example/
├── First.java
└── Second.java
~~~

`First.java`:

~~~java
package example;

import module java.base;

public class First {
    List<String> names = List.of("A", "B");
}
~~~

`Second.java`:

~~~java
package example;

public class Second {
    // Không có import trong file này:
    // List<String> names = List.of("A"); // không phân giải được List

    java.util.List<String> names = java.util.List.of("A");
}
~~~

Dù hai file đều ở package `example`, câu `import module java.base;` trong `First.java` không ảnh hưởng `Second.java`.

Import cũng **không truyền sang package con**, không giúp các file được biên dịch cùng lượt tự thấy simple name và không trở thành API mà JAR “xuất ra” cho người dùng.

### 7.2. Phạm vi bao gồm khai báo kiểu và nội dung bên trong

Trong một ordinary compilation unit, tên import có thể được sử dụng trong các khai báo class/interface của file đó, gồm các thành viên và thân phương thức.

~~~java
package example;

import module java.base;

public class Library {
    private final List<String> titles = new ArrayList<>();

    public void add(String title) {
        titles.add(title);
    }

    public List<String> all() {
        return List.copyOf(titles);
    }
}

interface Timestamped {
    Instant createdAt();
}
~~~

`List`, `ArrayList`, `Instant` đều từ package được `java.base` export. Câu lệnh import ở đầu file có tác dụng đối với các khai báo kiểu trong cùng compilation unit, không chỉ với class đầu tiên.

### 7.3. Import không giúp tên trong chính các import khác

Các tên được đưa vào phạm vi bởi một import declaration **không có scope bên trong các import declaration khác trong cùng file**.

~~~java
import module java.base;
import static java.lang.Math.PI; // Dùng tên đầy đủ của Math

class Circle {
    double area(double r) {
        return PI * r * r;
    }
}
~~~

Không được giả định rằng sau `import module java.base;` ta có thể viết `import static Math.PI;`: tên ở vị trí import phải tuân thủ ngữ pháp và quy tắc định danh phù hợp, thay vì dùng một simple name nhờ import trước đó.

### 7.4. Module import trong module-info.java

JLS §7.3 cho phép **modular compilation unit** có import declarations trước khai báo module. Ví dụ:

~~~java
// module-info.java
import module java.sql;

module com.example.jdbcclient {
    requires java.sql;
    uses Driver; // java.sql.Driver
}
~~~

`Driver` được phân giải nhờ module import **trong chính file `module-info.java`**. Nó không biến `Driver` thành tên ngắn trong tất cả các class khác của module. Những class ấy vẫn cần import riêng hoặc dùng tên đầy đủ.

Đây là sự khác biệt giữa **scope của import** và **scope module**: module descriptor công bố dependencies và services, còn import chỉ hỗ trợ viết tên trong file descriptor.

### 7.5. package-info.java và annotations

Một file `package-info.java` có thể chứa package declaration/annotations và import declarations:

~~~java
@Deprecated
package example.api;

import module java.base;
~~~

Dùng `@Deprecated` ở đây chỉ minh họa cú pháp annotation trên package, **không** phải đề xuất đánh dấu một package thực tế là deprecated.

Import declaration có thể hỗ trợ tên kiểu được dùng trong **annotations của package declaration**, nhưng không làm các class khác của package tự có những simple name đó. Các import trong `package-info.java` không phải một chỗ đặt import chung cho cả package.

### 7.6. Compact source files và import ngầm định java.base

Ở Java 27, đối với **compact compilation unit** (compact source file theo cú pháp hiện hành), JLS §7.3 coi toàn bộ các public top-level types thuộc package được `java.base` export như đã có `import module java.base;` ngầm định.

Ví dụ một compact source file có instance main:

~~~java
void main() {
    List<String> names = List.of("Java", "Modules");
    System.out.println(names);
}
~~~

Trong ngữ cảnh compact source file, `List` có thể dùng không cần dòng `import module java.base;` tường minh.

**Không suy rộng quy tắc này sang ordinary compilation unit**: một class Java thông thường vẫn có implicit `java.lang.*`, chứ không mặc nhiên nhập cả `java.util.List`, `java.nio.file.Path`, v.v. nếu không có import thích hợp.

## 8. Va chạm simple name khi import nhiều module

### 8.1. Hai module có thể export các kiểu trùng tên

Ví dụ kinh điển:

- `java.base` export `java.util.List` (interface).
- `java.desktop` export `java.awt.List` (class).

Nếu import cả hai:

~~~java
import module java.base;
import module java.desktop;

public class Ambiguous {
    // Lỗi: List mơ hồ giữa java.util.List và java.awt.List.
    // List values;
}
~~~

Trong các phần sử dụng simple name `List` khi hai kiểu cùng là ứng viên và không bị shadow, compiler không thể chọn một kiểu tùy ý. Đây là **compile-time error khi sử dụng tên mơ hồ**, chứ không phải Java tự đổi theo thứ tự hai dòng import.

### 8.2. Một module duy nhất cũng có thể chứa tên trùng

Module `java.desktop` export nhiều package, trong đó:

- `javax.swing.text.Element` là interface.
- `javax.swing.text.html.parser.Element` là class.

Vì vậy:

~~~java
import module java.desktop;

class AmbiguousElement {
    // Element element; // tên có thể mơ hồ
}
~~~

Đừng giả định “chỉ import một module” thì chắc chắn mọi simple name đều duy nhất.

### 8.3. Giải quyết bằng single-type-import

~~~java
import module java.base;
import module java.desktop;

import java.util.List; // Chọn tường minh java.util.List.

public class ExplicitList {
    List<String> names = List.of("An", "Bình");
}
~~~

Theo JLS §6.4.1, **single-type-import** phù hợp sẽ shadow các kiểu cùng simple name được import bằng single-module-import. Đây là cách rõ ràng để giữ lợi ích module import nhưng chọn một tên cụ thể ở nơi có xung đột.

### 8.4. Giải quyết bằng fully qualified name

~~~java
import module java.base;
import module java.desktop;

public class QualifiedNames {
    java.util.List<String> names = java.util.List.of("A");
    java.awt.List legacyGuiWidget; // Chỉ minh họa tên kiểu khác.
}
~~~

Fully qualified name làm rõ loại kiểu đang được nhắc đến. Trong bài này, `java.awt.List` chỉ được dùng làm ví dụ **xung đột tên**, không phải khuyến nghị chọn AWT để phát triển giao diện mới.

Không cần “chữa” va chạm bằng cách đảo thứ tự các dòng import: Java không chọn kiểu import sau cùng theo quy tắc *last wins*.

### 8.5. Trùng import module không có hiệu ứng bổ sung

~~~java
import module java.base;
import module java.base;
~~~

Hai dòng cùng nhập một module được coi như một dòng về mặt hiệu ứng. JLS quy định các import trùng module (ngoài một dòng) là dư thừa, không bắt lỗi chỉ vì trùng tên module.

Trong code review, vẫn nên xóa dòng dư vì giảm nhiễu cho người đọc.

## 9. Shadowing: thứ tự ưu tiên khi có nhiều nguồn tên

### 9.1. Không được dùng thứ tự dòng import để giải thích

Một simple name có thể đến từ khai báo trong file, cùng package, implicit import, package-on-demand import, module import hoặc single-type-import.

Quy tắc **shadowing và obscuring** của JLS §6.4 quyết định ứng viên nào còn nhìn thấy. Không có quy tắc “module import đứng trước thắng” hay “module import đứng sau thắng”.

### 9.2. Single-type-import được ưu tiên hơn module import

~~~java
import module java.base;
import module java.desktop;
import java.util.List;

class Sample {
    List<String> items = List.of("X");
}
~~~

`List` ở `Sample` là `java.util.List` nhờ import tường minh.

### 9.3. Type-import-on-demand có thể shadow module import

JLS §6.4.1 quy định type-import-on-demand có thể shadow single-module-import khi chúng cùng đưa vào một simple name:

~~~java
import module java.base;
import module java.desktop;
import java.util.*;

class PackageDemandWins {
    List<String> values = List.of("A", "B");
}
~~~

Ở đây `java.util.*` đưa `java.util.List` vào phạm vi và shadow ứng viên `List` từ module import. Tuy nhiên, sử dụng single-type-import `import java.util.List;` thường thể hiện ý định rõ hơn.

Đây là khác biệt đáng chú ý: hai on-demand imports ở cấp **package** và **module** không phải lúc nào cũng được xử lý giống hai package-on-demand imports thông thường.

### 9.4. java.lang có implicit import mạnh hơn module import

Mọi compilation unit được coi như có `import java.lang.*;` ngầm định. Theo JLS §6.4.1, các kiểu từ implicit `java.lang.*` có thể shadow kiểu cùng tên được import nhờ single-module-import.

~~~java
import module java.base;

class Hello {
    String message = "Hello";
}
~~~

`String` đã có sẵn ngay cả khi bỏ module import, vì nó thuộc `java.lang`.

Không nên kết luận rằng `import module M;` sẽ thay thế tất cả cách phân giải simple name hiện có trong file: quy tắc shadowing của những khai báo khác vẫn áp dụng.

### 9.5. Khai báo kiểu trong cùng file hoặc scope gần hơn

Khai báo top-level/nested/local cũng tham gia quy tắc shadowing và obscuring. Ví dụ:

~~~java
import module java.base;

class Container {
    static final class List {
        // Kiểu riêng của Container.
    }

    List value; // Container.List, không phải java.util.List.
}
~~~

Một kiểu nested `List` trong `Container` có thể che khuất kiểu `List` có cùng simple name được đưa vào qua module import ở nơi nó có hiệu lực.

Nếu muốn dùng kiểu collection:

~~~java
class Container2 {
    static final class List {
    }

    java.util.List<String> names = java.util.List.of("A");
}
~~~

Fully qualified name tránh nhầm khi phạm vi gần đã có một khai báo trùng tên.

### 9.6. Bảng ghi nhớ về tên trùng

| Tình huống | Quy tắc thực tế |
|---|---|
| Hai module imports đưa hai kiểu `List` khác nhau | Có thể mơ hồ ở chỗ dùng simple name |
| Thêm `import java.util.List;` | Single-type-import giải quyết tên `List` |
| Thêm `import java.util.*;` | Theo JLS, package-on-demand import có thể shadow module import |
| `java.lang.String` và tên giống nó từ module import | Implicit `java.lang.*` được ưu tiên theo shadowing |
| Kiểu nested/local khai báo cùng tên | Xét scope và shadowing của khai báo gần |
| Viết `java.util.List` | Bỏ qua mơ hồ simple name `List` |
| Đảo thứ tự hai `import module` | Không giải quyết được mơ hồ |
| Import cùng module hai lần | Không tạo hiệu ứng mới |

## 10. Ví dụ thực hành: một file Java độc lập

Lưu thành `ModuleImportDemo.java` và biên dịch bằng JDK 27.

~~~java
import module java.base;

public class ModuleImportDemo {

    public static void main(String[] args) {
        List<String> technologies = List.of("Java", "JPMS", "JLS");

        List<String> upper = technologies.stream()
                .map(String::toUpperCase)
                .toList();

        Path file = Path.of("docs", "guide.txt");
        LocalDate releaseDay = LocalDate.of(2026, 11, 27);

        System.out.println(upper);
        System.out.println(file);
        System.out.println(releaseDay);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ModuleImportDemo.java
java ModuleImportDemo
~~~

Trong file này:

- `List` là `java.util.List`.
- `Path` là `java.nio.file.Path`.
- `LocalDate` là `java.time.LocalDate`.
- `String` và `System` vốn cũng đã được nhập ngầm qua `java.lang`.
- `import module java.base;` cho phép các simple name công khai thuộc những package khác nhau của `java.base` xuất hiện trong file.

Một module import không khiến runtime trả về kết quả khác với khi dùng các single-type-import tương đương. Đây là tính năng cải thiện **cách viết mã nguồn và phân giải tên ở compile time**.

## 11. Ví dụ thực hành: named module và module path

### 11.1. Cấu trúc minh họa

~~~text
src/
└── com.example.reports/
    ├── module-info.java
    └── com/
        └── example/
            └── reports/
                └── ReportApp.java
~~~

File `module-info.java`:

~~~java
module com.example.reports {
    requires java.sql;

    exports com.example.reports;
}
~~~

File `ReportApp.java`:

~~~java
package com.example.reports;

import module java.sql;

public final class ReportApp {

    public static void main(String[] args) {
        // DriverManager được export trực tiếp bởi java.sql.
        System.out.println(DriverManager.class.getModule().getName());

        // java.sql requires transitive java.logging.
        System.out.println(Logger.class.getModule().getName());

        // java.sql cũng requires transitive java.xml.
        System.out.println(
                DocumentBuilderFactory.class.getModule().getName());
    }
}
~~~

Ví dụ không cần kết nối database. Nó chỉ cho thấy ba tên kiểu được compiler phân giải từ module import và dependency transitive của `java.sql`.

### 11.2. Biên dịch và chạy

Tại thư mục cha của `src`:

~~~bash
javac -d mods --module-source-path src --module com.example.reports
java --module-path mods --module com.example.reports/com.example.reports.ReportApp
~~~

Kết quả dự kiến là tên các module chứa ba kiểu:

~~~text
java.sql
java.logging
java.xml
~~~

Điểm cần phân biệt: chương trình chạy được vì `com.example.reports` **đọc** `java.sql` qua `requires`, còn `java.sql` công bố transitive readability đến các module liên quan. Import chỉ giảm nhu cầu viết tên kiểu đầy đủ.

### 11.3. Nếu bỏ requires java.sql

Nếu sửa descriptor thành:

~~~java
module com.example.reports {
    exports com.example.reports;
}
~~~

trong khi không có quan hệ khác làm `java.sql` readable, `import module java.sql;` sẽ không hợp lệ. Không có cách “chỉ import ở file Java” để tránh khai báo dependency khi named module phải đọc module đó.

### 11.4. Import trong module-info.java là một phạm vi riêng

Có thể viết một modular compilation unit:

~~~java
import module java.sql;

module com.example.jdbcclient {
    requires java.sql;
    uses Driver; // Tên ngắn của java.sql.Driver.
}
~~~

Đây là một ví dụ **độc lập**, không phải file thứ ba cần thêm vào `com.example.reports` ở trên. Nếu cần `Driver` dưới dạng simple name trong `ReportApp.java`, file ấy vẫn phải import phù hợp, hoặc dùng tên `java.sql.Driver`.

## 12. Module import so với import cụ thể: chọn thế nào?

### 12.1. Khi module import hợp lý

Dùng `import module M;` khi:

- Một file thật sự sử dụng nhiều API từ nhiều package của cùng module.
- Module export một API nhất quán và việc gom import theo module giúp tập trung ý đồ.
- Code ngắn hoặc ví dụ học tập thường xuyên dùng nhiều lớp Java SE.
- Các tên kiểu ít trùng và nhóm phát triển thống nhất quy ước xử lý ambiguity.

Ví dụ một ứng dụng xử lý `Path`, `Files`, `List`, `Stream` và `LocalDate` đều nằm trong `java.base`, một `import module java.base;` có thể giảm nhiều dòng import.

### 12.2. Khi single-type-import dễ bảo trì hơn

Dùng những import cụ thể khi:

- File chỉ cần một hoặc hai kiểu của module.
- Hai module được import có nhiều simple name trùng.
- Khi review cần nhìn ngay những dependency kiểu quan trọng của file.
- Muốn tránh việc thêm một kiểu mới được export từ module về sau khiến simple name đang dùng trở nên mơ hồ.
- Có quy ước nội bộ về cách import hoặc định dạng mã.

Ví dụ:

~~~java
import java.util.List;
import java.nio.file.Path;
~~~

Nếu chỉ cần hai kiểu này, hai single-type-import có thể dễ hiểu hơn import cả `java.base`.

Không có quy tắc bắt buộc rằng module import là “hiện đại hơn” trong mọi tình huống. Nó là lựa chọn cú pháp chính thức, còn chất lượng API và khả năng bảo trì phụ thuộc ngữ cảnh.

### 12.3. Có thể phối hợp linh hoạt

~~~java
import module java.base;
import java.util.List;

class HybridImports {
    List<String> values = List.of("A", "B");
    Path file = Path.of("data.txt");
}
~~~

Import `List` tường minh có thể hữu ích nếu tác giả muốn thể hiện lựa chọn rõ ràng khi có nguy cơ trùng tên, còn các kiểu khác vẫn dùng qua module import.

### 12.4. Không import để vượt giới hạn encapsulation

Module import không phải cơ chế cấp phép. Nó không:

- Tự thêm `requires M;` trong `module-info.java`.
- Tự biến package không export thành public API.
- Thay `opens` hay cho phép deep reflection vào package đóng.
- Tự làm một module tùy biến trên module path được giải quyết/đọc nếu cấu hình không cho phép.
- Tự tạo dependency runtime để gọi service provider.
- Tự import static members hoặc nested types như simple names độc lập.

Những khả năng trên do các quy tắc khác của Java và JPMS kiểm soát.

## 13. Lỗi thường gặp và hướng khắc phục

| Nhầm lẫn hoặc lỗi | Cách hiểu và hướng sửa |
|---|---|
| Viết `import module java.util;` | `java.util` là package; dùng `java.base` hoặc `import java.util.*;` |
| Viết `import module java.base.*;` | Module import không có dấu `*` |
| Cho rằng module import thay `requires` | Named module vẫn phải đọc module theo JPMS |
| Cho rằng import làm package nội bộ thành public | Chỉ những kiểu thật sự accessible mới được dùng |
| Nghĩ import có scope toàn package/module | Scope thuộc compilation unit chứa import |
| Mong `import module java.base;` import static `PI` | Cần `Math.PI` hoặc static import tương ứng |
| Mong tên `Entry` xuất hiện vì `Map` được import | Nested type không tự có simple name; dùng `Map.Entry` hoặc import riêng |
| Nghĩ `import java.util.*;` nhập `Stream` | `java.util.stream` là package khác |
| Nghĩ mọi `requires` của M đều import transitively | Chỉ các module được đọc nhờ quan hệ readability thích hợp |
| Nghĩ `import module java.se;` có nghĩa mọi kiểu JDK | Chỉ tập module và package liên quan được export/readable |
| Đảo thứ tự hai module import để chọn `List` | Không có ưu tiên theo thứ tự dòng; dùng single-type-import hoặc FQN |
| Cho rằng chỉ có nhiều module import mới mơ hồ | Một module cũng có thể export nhiều package trùng simple name |
| Tưởng package-info import áp dụng cho mọi file trong package | Chỉ compilation unit `package-info.java` |
| Tưởng module-info import áp dụng cho mọi class trong module | Import ở `module-info.java` chỉ giúp tên trong descriptor ấy |
| Nghĩ ordinary class tự có mọi API java.base như compact source file | Ordinary unit chỉ có implicit `java.lang.*`, còn compact unit có quy tắc implicit riêng |
| Lặp lại `import module M;` để tăng hiệu quả | Các import trùng module được coi là dư thừa |

## 14. Checklist khi đọc hoặc review một file có module import

Khi gặp `import module M;`, lần lượt hỏi:

1. `M` là **module name** hay chỉ là tên package?
2. File hiện nằm trong **named module**, **unnamed module** hay **compact source file**?
3. Module hiện tại có **đọc được M** theo graph đã resolve không?
4. `M` export những package nào cho module hiện tại?
5. `M` có những dependency `requires transitive` nào đưa thêm exported packages vào phạm vi không?
6. Tên kiểu được dùng có thực sự là **public top-level** và **accessible** không?
7. File có single-type-import, package-on-demand import, nested type hoặc tên trong scope gần có thể shadow không?
8. Simple name có thể đến từ nhiều package khác nhau và gây ambiguity không?
9. Một tên như `Map.Entry` cần truy cập thông qua outer type thay vì simple name `Entry` không?
10. File khác cùng package có import riêng chưa?
11. `module-info.java` đã khai báo dependency thích hợp chưa, hay chỉ đang dùng import như thể nó là requires?
12. Dùng module import có thật sự tăng tính dễ đọc so với import cụ thể trong file này không?

## 15. Bài tập tự kiểm tra

1. Vì sao `import module java.base;` cho phép dùng cả `List` và `Path` mà `import java.util.*;` không cho dùng `Path`?
2. `import module M;` có thực thi class initialization hoặc tạo object nào không?
3. Với module `M1` có `requires M5;` nhưng không có `requires transitive M5;`, import `M1` có tự kéo tên từ `M5` không?
4. Vì sao `exports p2 to M0;` có thể cho phép `M0` thấy kiểu trong `p2` nhưng không cho phép module khác thấy chúng?
5. Điều gì xảy ra nếu `M0` không đọc `M1` nhưng source lại viết `import module M1;`?
6. Tác dụng của module import trong `First.java` có lan sang `Second.java` cùng package không?
7. Vì sao `List` có thể mơ hồ khi import đồng thời `java.base` và `java.desktop`?
8. Một module duy nhất có thể tạo ambiguity cho simple name hay không? Hãy nêu ví dụ.
9. `import java.util.List;` thay đổi cách phân giải tên `List` thế nào khi file đã import cả hai module trên?
10. `import java.util.*;` và `import module java.base;` có mức ưu tiên shadowing giống nhau không?
11. Vì sao `String` có sẵn trong ordinary Java file ngay cả khi không dùng `import module java.base;`?
12. `import module java.sql;` có thể làm `Logger` và `DocumentBuilderFactory` có sẵn không, và vì sao?
13. Import ở `module-info.java` có làm `ReportApp.java` tự thấy `Driver` không?
14. Một compact source file Java 27 có quy tắc implicit import khác ordinary compilation unit như thế nào?
15. Việc chọn single-type-import hay module import ảnh hưởng thế nào đến rủi ro trùng tên và khả năng bảo trì?

## 16. Tài liệu tham khảo chính thức

- [JLS Java SE 27 — §7.5 Import Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.5): năm dạng import, phạm vi và điều kiện sử dụng.
- [JLS Java SE 27 — §7.5.5 Single-Module-Import Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.5.5): cú pháp `import module M;`, exported packages, readability, transitive dependencies và name ambiguity.
- [JLS Java SE 27 — §7.3 Compilation Units](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.3): ordinary, compact và modular compilation units; implicit imports.
- [JLS Java SE 27 — §6.3 Scope of a Declaration](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.3): phạm vi tên nhập trong compilation unit.
- [JLS Java SE 27 — §6.4.1 Shadowing](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.4.1): quy tắc ưu tiên single-type, package-on-demand và module import.
- [JLS Java SE 27 — §7.7 Module Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.7): cấu trúc `module-info.java`, `requires` và `exports`.
- [Java SE 27 API — module java.sql](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/module-summary.html): public exports và indirect exports qua `java.logging`, `java.xml`.
- [Java SE 27 API — module java.se](https://docs.oracle.com/en/java/javase/27/docs/api/java.se/module-summary.html): vai trò aggregator module và các package được export gián tiếp.
- [Oracle Java 25 Language Guide — Module Import Declarations](https://docs.oracle.com/en/java/javase/25/language/module-import-declarations.html): mô tả tính năng khi trở thành chính thức (còn áp dụng cho Java 27).
