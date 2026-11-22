# Package tổ chức tên kiểu và tránh trùng tên — Java 17+

## 1. Package là không gian tên của các kiểu Java

**Package** là một **không gian tên (namespace)** và một cách nhóm các kiểu có liên quan trong ứng dụng Java: class, interface, enum, record. Khi dự án có nhiều lớp, package giúp người đọc biết lớp thuộc chức năng nào và giúp các kiểu có **tên đơn giản trùng nhau** vẫn tồn tại hợp lệ nếu chúng nằm ở những package khác nhau.

Ví dụ:

~~~text
com.example.sales.Report
com.example.support.Report
~~~

Cả hai đều là lớp có tên đơn giản `Report`, nhưng **tên đầy đủ có package khác nhau**. Vì vậy, Java phân biệt được báo cáo bán hàng với báo cáo hỗ trợ, không cần ép tất cả các class phải có tên đơn giản duy nhất trên toàn dự án.

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Package name | `com.example.sales` | Không gian tên chứa kiểu |
| Simple name | `Report` | Tên lớp tại nơi khai báo |
| Qualified type name | `com.example.sales.Report` | Chỉ chính xác kiểu cùng package của nó |
| Another qualified name | `com.example.support.Report` | Một kiểu khác, dù simple name giống nhau |

Tên package được khai báo **bằng mã Java**, không phải tự động lấy từ tên thư mục. Các thư mục nguồn thường được sắp cho khớp namespace để xây dựng và quản lý thuận tiện.

## 2. Namespace xác định danh tính kiểu

Hai kiểu `com.example.sales.Report` và `com.example.support.Report` có cùng **simple name** `Report` nhưng tên đầy đủ khác nhau, nên là **hai kiểu riêng biệt**. Với mã nguồn:

~~~java
package com.example.sales;

public class Report {
    public String kind() { return "sales"; }
}
~~~

`package` xác định namespace, nằm trước khai báo `import` và top-level type. Theo quy ước, package được đặt tên chữ thường theo lĩnh vực hoặc tên miền đảo ngược; cấu trúc nguồn và cú pháp đầy đủ được thực hành ở bài tiếp theo.

## 3. Cây nguồn tương ứng với tên package

~~~text
project/
└── src/
    └── com/example/
        ├── sales/Report.java
        ├── support/Report.java
        └── app/Main.java
~~~

Cả hai `Report.java` cùng tồn tại nhờ hai namespace khác nhau. Tên package được quyết định bởi khai báo trong mã; **thư mục khớp package** là cách tổ chức thực tế giúp công cụ tìm nguồn. `javac -d out` tạo cây `.class` theo package trong `out`; `out` là classpath root khi chạy.

## 4. Hai kiểu cùng simple name vẫn không trùng nhau

Trong `src/com/example/support/Report.java` có thể khai báo một `public class Report` khác:

~~~java
package com.example.support;

public class Report {
    public String kind() { return "support"; }
}
~~~

Điều kiện tránh va chạm là **tên kiểu đầy đủ khác nhau**. Nếu hai top-level type có cùng tên đầy đủ trong cùng môi trường biên dịch thì không thể xem chúng là hai class riêng mang cùng tên. Hai kiểu trong ví dụ còn mang hành vi riêng: `kind()` lần lượt trả `"sales"` và `"support"`.

## 5. Dùng cả hai lớp trong mã nguồn thứ ba

~~~java
package com.example.app;

import com.example.sales.Report;

class Main {
    Report sales = new Report();
    com.example.support.Report support =
            new com.example.support.Report();
}
~~~

Import cho phép rút gọn tên **một kiểu cụ thể**; lớp còn lại dùng qualified name. Import không đổi danh tính lớp, không sao chép code, không tạo object và không thêm thư viện vào classpath. Java không hỗ trợ `import ... as ...`.

## 6. Chung tiền tố package vẫn là package khác

`com.example`, `com.example.sales` và `com.example.sales.audit` không phải cùng package chỉ vì tên lồng tiền tố. Do đó `import com.example.*;` không tự nhập `com.example.sales.Report`. Package có quan hệ tên nhưng không tự kế thừa quyền package-private. Bài về wildcard import và package con sẽ phân tích cụ thể giới hạn này.

## 7. Tổ chức nhóm kiểu theo trách nhiệm

`sales` và `support` thể hiện vùng chức năng, giúp người đọc tìm đúng kiểu. Một package không thay thế thiết kế API hay module; nó chỉ mang lại không gian tên và tham gia một số quy tắc truy cập. Chọn package theo trách nhiệm liên quan và giữ tên nhất quán thay vì dồn mọi class vào cùng một package lớn.

## 8. Package và mức truy cập có quan hệ nhưng khác nhiệm vụ

Package chủ yếu tổ chức **namespace**. Java còn dùng khái niệm **cùng package** khi kiểm tra một số quyền truy cập.

| Khai báo | Ý nghĩa cơ bản |
|---|---|
| `public class Report` | Có thể được tham chiếu từ package khác nếu đáp ứng các điều kiện truy cập/classpath/module |
| `class Helper` (không modifier, top-level) | **Package-private**: chỉ các kiểu trong cùng package được phép truy cập |
| `public void print()` | Public method khi nơi gọi có quyền truy cập tới lớp và method |
| `void internal()` (không modifier) | Package-private method |
| `private int count` | Private member; lớp top-level khác cùng package không tự được truy cập |

Ví dụ, một class `com.example.sales.InternalHelper` không khai báo `public` ở mức top-level sẽ **không tự truy cập được** từ `com.example.support`. Các tên `com.example.sales` và `com.example.sales.audit` cũng không phải **cùng package** theo quy tắc package-private.

Package không thay thế `private`, `public`, `protected` hoặc các quy tắc Java module. Đồng thời, cùng namespace không có nghĩa là “đã có cơ chế bảo mật tuyệt đối”: đây là quy tắc tổ chức kiểu và kiểm tra quyền truy cập của ngôn ngữ.

## 9. Ví dụ Java 17+ hoàn chỉnh, chạy được

Tạo **đúng ba file** theo cấu trúc thư mục ở mục 3. Mỗi lớp có package và public class riêng; hai file `Report.java` không xung đột vì tên đầy đủ khác nhau.

**File 1 — `src/com/example/sales/Report.java`:**

~~~java
package com.example.sales;

public final class Report {
    private final String title;

    public Report(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("blank sales title");
        }
        this.title = title.strip();
    }

    public String describe() {
        return "sales:" + title;
    }
}
~~~

**File 2 — `src/com/example/support/Report.java`:**

~~~java
package com.example.support;

public final class Report {
    private final String ticket;

    public Report(String ticket) {
        if (ticket == null || ticket.isBlank()) {
            throw new IllegalArgumentException("blank ticket");
        }
        this.ticket = ticket.strip();
    }

    public String describe() {
        return "support:" + ticket;
    }
}
~~~

**File 3 — `src/com/example/app/Main.java`:**

~~~java
package com.example.app;

import com.example.sales.Report;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        Report sales = new Report(" Q1 ");
        com.example.support.Report support =
                new com.example.support.Report("Ticket-7");

        System.out.println("sales=" + sales.describe());
        System.out.println("support=" + support.describe());
        System.out.println("sales type=" + sales.getClass().getName());
        System.out.println("support type=" + support.getClass().getName());
        System.out.println("simple names="
                + sales.getClass().getSimpleName() + ","
                + support.getClass().getSimpleName());
        System.out.println("same class="
                + (sales.getClass() == support.getClass()));
        System.out.println("sales package="
                + sales.getClass().getPackageName());
        System.out.println("support package="
                + support.getClass().getPackageName());
    }
}
~~~

Đoạn `Main` dùng `import com.example.sales.Report;` cho sales và **fully qualified type name** cho support. Hai biến giữ hai đối tượng khác kiểu, dù hai class đều có simple name `Report`.

### Biên dịch và chạy bằng CLI

**Yêu cầu:** JDK 17 trở lên. Đứng tại thư mục dự án chứa thư mục `src`. Dùng `-d out` để biên dịch file `.class` vào package path trong `out`. Không cần Maven/Gradle, thư viện ngoài hay preview features.

**Bash (Linux/macOS):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/com/example/sales/Report.java src/com/example/support/Report.java src/com/example/app/Main.java
java -cp out com.example.app.Main
~~~

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out .\src\com\example\sales\Report.java .\src\com\example\support\Report.java .\src\com\example\app\Main.java
java -cp out com.example.app.Main
~~~

Các file biên dịch nằm ở:

~~~text
out/
└── com/
    └── example/
        ├── sales/Report.class
        ├── support/Report.class
        └── app/Main.class
~~~

`out` là **classpath root**. Khi chạy, hãy dùng `com.example.app.Main` (tên lớp có package), không dùng `java Main` hoặc `java -cp out Main`.

### Exact expected stdout

~~~text
sales=sales:Q1
support=support:Ticket-7
sales type=com.example.sales.Report
support type=com.example.support.Report
simple names=Report,Report
same class=false
sales package=com.example.sales
support package=com.example.support
~~~

**Giải thích:** Hai kiểu có simple name giống nhau, nhưng `getClass().getName()` cho ra tên đầy đủ khác nhau, `same class=false`. `getClass().getPackageName()` xác nhận hai namespace. Mỗi lớp thực thi hành vi `describe()` của chính nó.

## 10. Các lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách xử lý |
|---|---|---|
| Coi hai `Report` thuộc hai package là một kiểu | Package khác nên kiểu khác | Dùng tên đầy đủ để phân biệt |
| Tạo hai top-level `Report` trong cùng package | Trùng tên kiểu trong cùng namespace | Đổi tên kiểu hoặc chuyển package phù hợp |
| Đưa hai single-type import cho hai `Report` vào cùng file | Cạnh tranh simple name, lỗi biên dịch | Một import, kiểu kia viết tên đầy đủ |
| Nghĩ `import com.example.*;` bao gồm `com.example.sales` | Không import đệ quy các package có cùng tiền tố | Import đúng package |
| Đặt `package` sau `import` hoặc trong class | Vi phạm cú pháp compilation unit | Đặt package ở đầu file |
| Tên file `Foo.java` nhưng khai báo `public class Bar` | Sai quy tắc tên file public top-level type | Tên file `Bar.java` |
| Dùng `java Main` trong khi class là `com.example.app.Main` | Launcher không tìm đúng tên lớp | `java -cp out com.example.app.Main` |
| Đặt classpath là `out/com/example/app` | Sai classpath root của package path | Dùng `-cp out` |
| Tin rằng thư mục quyết định package bất chấp khai báo nguồn | Namespace lấy từ khai báo Java | Đồng bộ đường dẫn và tên package |
| Coi `com.example.sales` và `com.example.sales.audit` là cùng package | Tên có tiền tố chung không đồng nghĩa cùng package | Xác định đúng tên package |
| Nghĩ `import` làm JVM chạy constructor ngay | Import là cơ chế tra cứu tên lúc biên dịch | Chỉ tạo object bằng hành vi khởi tạo tương ứng |

## 11. Bài tập và đáp án

**A.** Hai kiểu `org.acme.account.User` và `org.acme.audit.User` có được tồn tại cùng một chương trình không?  
**Đáp án:** **Có**, vì thuộc các package khác nhau và có tên kiểu đầy đủ khác nhau.

**B.** Với `com.example.sales.Report`, đâu là tên đơn giản và package?  
**Đáp án:** simple name là `Report`; package là `com.example.sales`.

**C.** Một file đã `import com.example.sales.Report;` thì làm sao tạo `Report` của support?  
**Đáp án:**

~~~java
com.example.support.Report support =
        new com.example.support.Report("Ticket-7");
~~~

**D.** `import com.example.*;` có tự nhập lớp `com.example.sales.Report` không?  
**Đáp án:** **Không**. Cần import trực tiếp `com.example.sales.Report` hoặc sử dụng tên đầy đủ.

**E.** Sau khi biên dịch `com.example.app.Main` vào `out/com/example/app/Main.class`, cần chạy lệnh nào từ thư mục dự án?  
**Đáp án:**

~~~bash
java -cp out com.example.app.Main
~~~

**F.** Trong package `com.example.sales`, một top-level `class Helper` không có `public` có thể được gọi từ `com.example.support` không?  
**Đáp án:** **Không**, vì `Helper` có quyền truy cập package-private và hai package khác nhau.

## 12. Checklist và kết luận

- [ ] Hiểu package tạo **không gian tên** và nhóm các kiểu liên quan.
- [ ] Phân biệt **simple name** với **tên kiểu đầy đủ có package**.
- [ ] Giải thích được vì sao hai lớp `Report` ở hai package không xung đột.
- [ ] Đặt khai báo `package ...;` đúng vị trí và đúng cú pháp.
- [ ] Tổ chức thư mục nguồn phù hợp với tên package.
- [ ] Dùng `import` hoặc tên đầy đủ khi cần sử dụng kiểu từ package khác.
- [ ] Biết Java không có `import ... as ...` và không có quy tắc “import cuối thắng”.
- [ ] Hiểu `package.*` không bao gồm những package khác có cùng tiền tố.
- [ ] Nhận diện package-private access và phân biệt với nhiệm vụ namespace.
- [ ] Biên dịch bằng `javac -d out` và chạy bằng tên main class đầy đủ.
- [ ] Chạy cả ba file Java 17+ và đối chiếu đúng stdout.

**Kết luận:** Package tổ chức mã thành **những không gian tên riêng biệt**. `com.example.sales.Report` và `com.example.support.Report` không trùng tên kiểu đầy đủ dù cùng được gọi ngắn là `Report`. Để sử dụng đúng lớp, hãy thống nhất tên package, đường dẫn nguồn, `import`/qualified name và classpath khi biên dịch, chạy chương trình.