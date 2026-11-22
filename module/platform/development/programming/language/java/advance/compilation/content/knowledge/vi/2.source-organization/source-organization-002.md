# Package, thư mục gốc và tên kiểu đầy đủ trong Java

Trong Java, **package** xác định không gian tên của một kiểu; **thư mục gốc mã nguồn** (source root) là điểm bắt đầu để công cụ build tìm các tệp nguồn; còn **tên kiểu đầy đủ** (fully qualified name, FQN) xác định một kiểu bằng tên package và tên kiểu. Ba khái niệm liên quan chặt chẽ nhưng không đồng nhất. Hiểu đúng chúng giúp biên dịch, chạy chương trình, thiết kế thư viện và xử lý lỗi import/classpath chính xác.

## 1. Ba khái niệm và mối quan hệ

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Package | Gom các kiểu vào một không gian tên và ảnh hưởng đến quyền truy cập package-private | `com.acme.catalog` |
| Thư mục gốc mã nguồn | Thư mục cha của cây thư mục tương ứng với tên package; do dự án/công cụ build quy định | `src/main/java` hoặc `src` |
| Tên kiểu đầy đủ | Tên để phân biệt kiểu với các kiểu có cùng tên ngắn ở package khác | `com.acme.catalog.Book` |
| Thư mục đầu ra | Nơi compiler ghi các tệp `.class`, thường phân cấp theo package | `out` hoặc `build/classes/java/main` |
| Classpath root | Thư mục/JAR mà compiler hoặc JVM dùng làm gốc để tìm binary class theo tên | `out` hoặc `app.jar` |

Với một tệp nguồn thông thường:

~~~text
project/
└── src/main/java/                   ← source root
    └── com/acme/catalog/            ← đường dẫn tương ứng package
        └── Book.java                ← compilation unit
~~~

Tệp `Book.java` có thể khai báo:

~~~java
package com.acme.catalog;

public class Book {
}
~~~

Khi đó tên đầy đủ của lớp là `com.acme.catalog.Book`. **Không** đưa `src`, `main` hay `java` vào tên package: chúng là phần của cấu trúc dự án, không phải một phần của định danh kiểu.

Một cách hình dung:

~~~text
source root      + package path          + source file
src/main/java/   + com/acme/catalog/     + Book.java

package name     + "." + simple name     = fully qualified name
com.acme.catalog + "." + Book            = com.acme.catalog.Book

classpath root   + binary path
out/             + com/acme/catalog/Book.class
~~~

Cây thư mục có dấu `/` hoặc `\` theo hệ điều hành; tên package trong Java **luôn** phân tách bằng dấu chấm (`.`).

## 2. Câu lệnh package: cú pháp và ý nghĩa

Khai báo package nằm trước các import và các khai báo kiểu ở cấp trên cùng, ngoại trừ comment và annotation áp dụng cho package.

~~~java
package com.acme.catalog;

import java.util.List;

public final class BookRepository {
    private final List<String> titles = List.of("Java", "JVM");

    public List<String> titles() {
        return titles;
    }
}
~~~

Một tệp nguồn chỉ có tối đa một khai báo `package`. Các lớp, interface, enum và record ở cấp trên cùng trong compilation unit này cùng thuộc package đã khai báo. Nếu không có khai báo `package`, các kiểu ở **unnamed package** (thường gọi là default package).

### Quy ước đặt tên

- Ưu tiên tên package chữ thường và cấu trúc có ý nghĩa: `com.example.compiler`, `org.example.parser.ast`. Thường bắt đầu bằng tên miền đảo ngược để hạn chế trùng tên giữa tổ chức.
- Mỗi thành phần giữa hai dấu chấm phải là định danh Java hợp lệ. Không dùng dấu gạch ngang như `java-compiler`, không bắt đầu bằng chữ số, không dùng từ khóa như `class`.
- Giữ tên ổn định vì đổi tên package sẽ làm thay đổi tên kiểu đầy đủ, import, classpath và có thể ảnh hưởng khả năng tương thích nhị phân hoặc serialization.
- `com.acme` và `com.acme.internal` là **hai package khác nhau**: tên có quan hệ dạng tiền tố không tạo ra quyền truy cập kế thừa giữa chúng.

Package là **không gian tên** và một phần của mô hình kiểm soát truy cập, không phải tiến trình độc lập, không tự động tạo module, và không tự đảm bảo cấu trúc thư mục vật lý.

## 3. Source root và vị trí tệp nguồn

Công cụ xây dựng dự án thường quy định các source root:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/                   ← mã ứng dụng
│   │       └── com/acme/app/Main.java
│   └── test/
│       └── java/                   ← mã kiểm thử
│           └── com/acme/app/MainTest.java
└── build/                          ← đầu ra (ví dụ Gradle)
~~~

`src/main/java` là quy ước phổ biến của Maven/Gradle, **không phải từ khóa hay quy tắc bắt buộc của ngôn ngữ Java**. Dự án nhỏ có thể chọn `src`, và trình biên dịch dòng lệnh có thể nhận tên đường dẫn tệp nguồn tường minh.

Khi tổ chức dự án, nên đặt tệp khai báo `package com.acme.app;` dưới `<source-root>/com/acme/app/`. Việc đồng bộ này giúp IDE, javac, test runner và build tool định vị tệp một cách dự đoán được. Với tên package `com.acme.app`, source root chính là thư mục **ngay phía trên** `com`, không phải thư mục `app`.

Không suy ra package từ vị trí tệp trong editor: trong Java thông thường, **khai báo `package` quyết định package**; vị trí trên đĩa là quy ước công cụ và cách tổ chức. Cũng không nên coi classpath root và source root là một: đầu vào chứa `.java`, còn classpath khi chạy phải trỏ đến các `.class` đã biên dịch hoặc JAR chứa chúng.

## 4. Ví dụ đầy đủ: biên dịch và chạy Java 17+

Tạo đúng hai tệp sau từ thư mục dự án:

~~~text
example/
└── src/
    └── com/
        └── acme/
            ├── catalog/
            │   └── Book.java
            └── app/
                └── Main.java
~~~

**Tệp `src/com/acme/catalog/Book.java`:**

~~~java
package com.acme.catalog;

public final class Book {
    private final String title;

    public Book(String title) {
        this.title = title;
    }

    public String title() {
        return title;
    }
}
~~~

**Tệp `src/com/acme/app/Main.java`:**

~~~java
package com.acme.app;

import com.acme.catalog.Book;

public final class Main {
    public static void main(String[] args) {
        Book book = new Book("Java 17");
        System.out.println(book.title());
        System.out.println(Book.class.getName());
    }
}
~~~

Từ thư mục `example`, chạy (PowerShell, Command Prompt hoặc shell Unix; tạo `out` trước nếu chưa có):

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/acme/catalog/Book.java src/com/acme/app/Main.java
java -cp out com.acme.app.Main
~~~

**Stdout chính xác:**

~~~text
Java 17
com.acme.catalog.Book
~~~

Sau lệnh biên dịch:

~~~text
example/
├── src/
│   └── com/acme/...                ← hai tệp .java
└── out/                            ← classpath root khi chạy
    └── com/acme/
        ├── catalog/Book.class
        └── app/Main.class
~~~

Giải thích từng bước:

1. `javac` nhận **đường dẫn tệp nguồn** sau các tùy chọn; ở đây chỉ định cả hai tệp `.java`.
2. `-d out` chỉ thư mục đích; compiler ghi các `.class` bên dưới nó theo tên package. `-encoding UTF-8` xác định encoding khi đọc mã nguồn.
3. `java -cp out` thêm `out` vào classpath. JVM tìm `com.acme.app.Main` dưới `out/com/acme/app/Main.class`.
4. Đối số cuối cho `java` là **tên lớp đầy đủ**, không phải `Main.java`, `Main.class` hay đường dẫn `out/com/acme/app/Main.class`.
5. `Main` dùng `Book` của package khác qua khai báo `import`. Compiler vẫn cần tìm được định nghĩa `Book` khi biên dịch; JVM vẫn cần tìm được `Book.class` khi chạy.

Nếu muốn gói các class đã biên dịch vào JAR dùng classpath, có thể chạy:

~~~bash
jar --create --file app.jar -C out .
java -cp app.jar com.acme.app.Main
~~~

JAR này chứa các entry `com/acme/app/Main.class` và `com/acme/catalog/Book.class`; thư mục `com` nằm ngay ở gốc JAR. Đây là cách chạy bằng classpath với tên main class tường minh, không yêu cầu manifest `Main-Class`.

## 5. Tên ngắn, tên đầy đủ và import

**Simple name** của `com.acme.catalog.Book` là `Book`. Để sử dụng một kiểu từ package khác, có thể import tên của nó:

~~~java
import com.acme.catalog.Book;

// Bên trong khai báo lớp:
Book book = new Book("Clean Code");
~~~

Hoặc sử dụng tên đầy đủ mà không cần import:

~~~java
// Bên trong khai báo lớp:
com.acme.catalog.Book book =
        new com.acme.catalog.Book("Clean Code");
~~~

Hai cách chỉ khác cách viết tên trong mã nguồn. `import` không copy mã, không tự cài dependency, không thêm JAR vào classpath và không điều khiển việc tải class lúc chạy.

Java tự cho phép dùng tên đơn giản của các kiểu nhìn thấy trong cùng package và tự có import ngầm cho `java.lang` (ví dụ `String`, `System`). Với các package khác, viết import hoặc tên đầy đủ khi cần. `import java.util.*;` chỉ import-on-demand các kiểu trong **chính** package `java.util`, không bao gồm `java.util.concurrent`.

### Khi hai kiểu trùng tên

Ví dụ `java.util.Date` và `java.sql.Date` có cùng simple name. Có thể dùng:

~~~java
java.util.Date legacyDate = new java.util.Date();
java.sql.Date sqlDate = new java.sql.Date(0L);
~~~

Hoặc chỉ import một trong hai và viết tên đầy đủ cho kiểu còn lại. Nếu hai import đơn kiểu cùng simple name gây xung đột thì compiler sẽ báo lỗi; với các import-on-demand, việc tham chiếu một tên mơ hồ cũng gây lỗi biên dịch. **Tên đầy đủ giải quyết sự mơ hồ**, miễn là kiểu đó có thể truy cập và dependency cần thiết có trên đường tìm kiếm của compiler.

Import tĩnh là khái niệm khác: `import static java.lang.Math.PI;` cho phép gọi tên thành viên tĩnh `PI` trực tiếp; nó không thay đổi package của lớp đang viết.

## 6. Tên đầy đủ, tên chuẩn và tên nhị phân

Ở mức cơ bản, tên kiểu đầy đủ của top-level class như `com.acme.catalog.Book` là tổ hợp `package + "." + tên kiểu`. Với **kiểu lồng nhau**, cần phân biệt cách viết trong mã nguồn với tên nhị phân dùng trong bytecode và nhiều API reflection:

~~~java
package com.acme.catalog;

public class Outer {
    public static class Inner {
    }
}
~~~

| Cách gọi | Giá trị |
| --- | --- |
| Tên đơn của kiểu lồng | `Inner` |
| Tên chuẩn (canonical name) | `com.acme.catalog.Outer.Inner` |
| Tên nhị phân (binary name) | `com.acme.catalog.Outer$Inner` |
| Đường dẫn file class sau compile | `com/acme/catalog/Outer$Inner.class` |
| `Outer.Inner.class.getCanonicalName()` | `com.acme.catalog.Outer.Inner` |
| `Outer.Inner.class.getName()` | `com.acme.catalog.Outer$Inner` |

Trong mã Java, ta thường viết `Outer.Inner`; khi gọi `Class.forName("com.acme.catalog.Outer$Inner")`, phải sử dụng **binary name**. Dấu `$` trong file class ở ví dụ này biểu diễn tên kiểu lồng nhau. Đừng thay mọi dấu chấm thành dấu `$`: chỉ ranh giới của kiểu lồng mới được biên dịch theo quy tắc này.

Lưu ý thêm: anonymous class và local class không nhất thiết có canonical name; `getCanonicalName()` có thể trả `null`. Với mảng, `Class.getName()` dùng ký hiệu descriptor khác với tên kiểu trong mã nguồn. Vì vậy không xem `getName()`, `getCanonicalName()` và chuỗi import là những biểu diễn thay thế nhau trong mọi trường hợp.

## 7. Package và quyền truy cập

Quyền truy cập trong Java liên quan trực tiếp đến package:

| Thành viên/kiểu | Phạm vi cơ bản |
| --- | --- |
| Top-level kiểu `public` | Có thể được mã ở package khác tham chiếu nếu các giới hạn module/đường tìm kiếm cũng cho phép |
| Top-level kiểu không ghi `public` | Chỉ mã trong **cùng package** truy cập được |
| Thành viên không ghi modifier (package-private) | Chỉ mã trong cùng package truy cập được |
| Thành viên `private` | Bị giới hạn bởi quy tắc truy cập private của Java (bao gồm quan hệ nestmate) |
| Thành viên `protected` | Cùng package hoặc các trường hợp kế thừa hợp lệ theo quy tắc Java |

Ví dụ:

~~~java
package com.acme.catalog;

final class CatalogValidator {
    static boolean valid(String title) {
        return title != null && !title.isBlank();
    }
}
~~~

`CatalogValidator` không có modifier `public`, vì thế `com.acme.catalog.Book` có thể dùng nó, nhưng `com.acme.app.Main` thì không. Tương tự, `com.acme.catalog.internal` là package riêng: một kiểu ở đó cũng **không** được quyền package-private của `com.acme.catalog`.

Một compilation unit Java thường chỉ có tối đa **một top-level public type**, và tên tệp phải tương ứng tên của kiểu public đó, ví dụ `public class Book` trong `Book.java`. Các top-level type không public khác có thể cùng nằm trong một tệp nếu hợp lệ, nhưng tổ chức mỗi kiểu ra tệp riêng thường dễ bảo trì hơn.

## 8. Unnamed package, package-info và module-info

**Unnamed package:** nếu bỏ khai báo `package`, lớp nằm trong unnamed package. Cách này tiện cho thử nghiệm nhỏ, nhưng không phù hợp với mã ứng dụng/thư viện nhiều package. Đặc biệt, mã trong một **named package không thể import kiểu từ unnamed package**. Khi xây dựng dự án, nên dùng named package rõ ràng.

**`package-info.java`:** tệp đặt tại thư mục của package, chủ yếu mang tài liệu Javadoc và annotation áp dụng cho package. Ví dụ:

~~~java
/**
 * Các kiểu miền nghiệp vụ phục vụ danh mục sách.
 */
package com.acme.catalog;
~~~

Tệp này không phải nơi khai báo lớp `Book` và không thay thế `Book.java`.

**`module-info.java` (JPMS, Java 9+):** mô tả **module**, là đơn vị bao gồm các package, khai báo dependency và package xuất bản. Hai lớp có package giống nhau không có nghĩa rằng dependency hoặc quyền truy cập module đã được cấu hình đúng. Ví dụ mô tả hai module riêng:

~~~java
// module-info.java của module com.acme.catalog
module com.acme.catalog {
    exports com.acme.catalog;
}
~~~

~~~java
// module-info.java của module com.acme.app
module com.acme.app {
    requires com.acme.catalog;
}
~~~

Trong ví dụ này, `exports` cho module khác truy cập public type thuộc package được xuất; package `com.acme.catalog.internal` không tự được xuất chỉ vì tên có tiền tố chung. `requires` diễn tả module dependency. Khi xây dựng ứng dụng JPMS, cần tổ chức module-source-path/module-path và lệnh chạy tương ứng; lệnh `java -cp` ở mục 4 dành cho dự án **classpath thông thường**, chưa phải ví dụ module-path.

## 9. Compiler tìm source và class như thế nào?

Có ba đường dẫn dễ bị nhầm:

- **Source path**: nơi `javac` có thể tìm thêm mã nguồn `.java` để biên dịch khi giải quyết các kiểu phụ thuộc (khi được cấu hình, ví dụ `-sourcepath src`). Đường dẫn các tệp `.java` nêu trực tiếp trong lệnh biên dịch luôn là đầu vào tường minh.
- **Compile classpath**: nơi `javac` tìm các kiểu đã biên dịch và thư viện JAR, cấu hình bằng `-classpath` hoặc `-cp`. Nó không được tự suy ra từ câu lệnh `import`.
- **Runtime classpath**: nơi lệnh `java` tìm class/JAR để thực thi, cũng cấu hình bằng `-cp` hoặc qua build tool. Đường dẫn này có thể khác compile classpath; thiếu thư viện lúc chạy có thể gây lỗi liên kết class.

Ví dụ với thư viện ngoài tên `lib/example.jar` và một tệp nguồn phụ thuộc vào nó (đường dẫn tệp chỉ mang tính minh họa):

~~~bash
javac -cp lib/example.jar -d out src/com/acme/app/Main.java
java -cp out:lib/example.jar com.acme.app.Main
~~~

Dấu phân cách **nhiều mục classpath** khác nhau theo hệ điều hành: Unix/macOS dùng `:`, Windows dùng `;`; trên Windows, đối số chạy tương ứng là `out;lib/example.jar` (nên đặt trong dấu nháy khi dùng shell để tránh cú pháp đặc biệt). Ví dụ thư viện ngoài này chỉ đúng khi tệp JAR và các dependency cần thiết thực sự tồn tại. Nếu mã phụ thuộc `Book.java` ở mục 4, cũng phải biên dịch `Book.java` hoặc đưa `Book.class`/JAR tương ứng vào compile classpath.

Bộ công cụ Maven/Gradle thường thay ta thiết lập source root, compile classpath, test classpath và thư mục output. IDE cũng suy ra các đường dẫn từ cấu hình dự án. Khi điều tra lỗi, hãy kiểm tra **cấu hình build thực tế** thay vì chỉ nhìn cây tệp trong giao diện.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/cách sửa |
| --- | --- | --- |
| `package ... does not exist` | Compiler không tìm thấy thư viện/class chứa package được import | Xác minh dependency và compile classpath, tên package, đường dẫn/tệp nguồn; `import` không tự tải dependency |
| `cannot find symbol: class Book` | Tên chưa resolve được tại vị trí sử dụng | Kiểm tra `package`, `import`, khả năng truy cập và kiểu đã được biên dịch |
| `class Book is public, should be declared in a file named Book.java` | Tên public top-level type khác tên tệp | Đổi tên tệp hoặc đổi tên kiểu cho khớp |
| `Could not find or load main class com.acme.app.Main` | Sai FQN, sai classpath root, hoặc thiếu class/dependency | Kiểm tra `out/com/acme/app/Main.class`, chạy `java -cp out com.acme.app.Main` từ đúng thư mục |
| `NoClassDefFoundError` | Một class cần lúc chạy không có/không tải được hoặc tên nhị phân không khớp | Kiểm tra nguyên nhân phía sau và runtime classpath; so sánh package khai báo, vị trí `.class` |
| `... is not public ... cannot be accessed from outside package` | Dùng top-level package-private type từ package khác | Sửa phạm vi API hoặc chuyển logic vào package phù hợp, không cố sửa bằng import |
| Tên `Date` bị ambiguous | Nhiều kiểu cùng simple name đang nhìn thấy | Chọn import cụ thể hoặc dùng tên đầy đủ ở nơi tham chiếu |
| IDE biên dịch được nhưng dòng lệnh không chạy | IDE đã tự cấu hình output/dependency còn lệnh `java` thiếu chúng | So sánh classpath/module-path, source root và working directory |

Một quy trình xử lý lỗi ngắn:

1. Mở tệp `.java`, đọc **chính xác** khai báo `package` và tên top-level public type.
2. Xác định source root được build tool khai báo, rồi kiểm tra đường dẫn dưới root theo các thành phần package.
3. Kiểm tra output có đúng `.class` dưới classpath root hay không.
4. Đối chiếu lệnh `javac` (nguồn, compile classpath, `-d`) và lệnh `java` (runtime classpath, main class FQN).
5. Nếu dùng module, kiểm tra `module-info.java`, `requires`, `exports`, module path; nếu dùng kiểu lồng, kiểm tra canonical name so với binary name.

## 11. Bài tập tự kiểm tra

**Bài 1.** Tệp `src/main/java/io/demo/tools/TextTool.java` chứa `package io.demo.tools;` và `public class TextTool {}`. Hãy xác định source root, simple name, FQN và đường dẫn class khi biên dịch với `-d classes`.

**Đáp án:** source root theo bố cục này là `src/main/java`; simple name `TextTool`; FQN `io.demo.tools.TextTool`; class file `classes/io/demo/tools/TextTool.class`.

**Bài 2.** Trong `com.acme.app.Main`, đổi `new Book("Java 17")` thành `new com.acme.catalog.Book("Java 17")`, bỏ import `Book`, sau đó biên dịch lại bằng lệnh ở mục 4. Kết quả stdout giữ nguyên vì hai cách tham chiếu cùng một kiểu.

**Bài 3.** Một lớp thuộc `com.acme.catalog.internal` muốn gọi phương thức package-private trong `com.acme.catalog.Book`. Có được không? **Không**: hai package khác nhau; muốn chia sẻ API qua ranh giới package cần thiết kế phạm vi truy cập thích hợp.

**Bài 4.** Vì sao `java -cp out Main` không tìm được lớp `Main` trong mục 4? Vì JVM tìm lớp thuộc unnamed package có tên `Main`, còn lớp đã biên dịch là `com.acme.app.Main`. Phải truyền FQN `com.acme.app.Main`.

## Ghi nhớ để áp dụng

- `package` quy định **không gian tên** của kiểu; source root và output root do cách xây dựng dự án quy định.
- Đường dẫn nguồn chuẩn: `<source-root>/<package-path>/<Type>.java`; đường dẫn bytecode chuẩn: `<output-root>/<package-path>/<Type>.class`.
- `import` rút ngắn cách viết tên kiểu trong mã nguồn, không cung cấp dependency.
- Khi chạy bằng classpath, JVM cần classpath root và **tên lớp đầy đủ**; không truyền đường dẫn tệp nguồn.
- Với nested type, phân biệt tên dùng trong Java source (dấu chấm) với binary name (thường có `$`).
- Package con không được hưởng quyền package-private của package cha; JPMS `exports`/ `requires` bổ sung các ranh giới module.
