# Cấu hình javac với srcdir, destdir và cấu trúc package

Trong Apache Ant, task `javac` gọi trình biên dịch Java để chuyển mã nguồn `.java` thành bytecode `.class`. Để trình biên dịch tìm đúng mã nguồn và ghi kết quả vào đúng vị trí, buildfile cần cấu hình rõ thư mục nguồn (`srcdir`), thư mục đầu ra (`destdir`) và cấu trúc package của mã Java.

Ba phần này liên hệ trực tiếp với nhau: `srcdir` xác định một hoặc nhiều source root; khai báo `package` trong từng tệp Java xác định tên đầy đủ của lớp; `destdir` là gốc nơi Ant ghi các thư mục package và tệp `.class`. Khi hiểu đúng quan hệ đó, có thể tổ chức mã nguồn dễ bảo trì, biên dịch nhiều package và tái sử dụng cấu hình trong các target khác nhau.

## 1. Task javac làm gì?

`javac` là task biên dịch Java tích hợp của Ant. Task xác định các tệp nguồn cần biên dịch, chuẩn bị classpath và gọi compiler adapter tương ứng với JDK được sử dụng.

Ví dụ tối thiểu:

```xml
<target name="compile">
    <mkdir dir="build/classes" />

    <javac
        srcdir="src"
        destdir="build/classes"
        includeantruntime="false" />
</target>
```

Trong ví dụ này:

- `srcdir="src"` xác định thư mục gốc chứa mã nguồn Java.
- `destdir="build/classes"` xác định thư mục gốc để ghi bytecode.
- `mkdir` bảo đảm thư mục đích tồn tại trước khi biên dịch.
- `includeantruntime="false"` tránh tự động đưa các thư viện runtime của Ant vào classpath biên dịch.

Nếu không chỉ định `destdir`, compiler có thể ghi các tệp `.class` cạnh tệp nguồn. Với một dự án có build output riêng, nên chỉ định `destdir` để giữ cây mã nguồn và cây kết quả tách biệt.

## 2. srcdir là source root

`srcdir` chỉ định thư mục gốc mà Ant dùng để tìm các tệp nguồn. Đường dẫn trong `srcdir` không phải là đường dẫn tới một package cụ thể; nó là điểm bắt đầu của cây package.

Ví dụ cấu trúc mã nguồn:

```text
project/
├── build.xml
└── src/
    └── com/
        └── example/
            └── app/
                ├── Main.java
                └── service/
                    └── GreetingService.java
```

Trong `Main.java`:

```java
package com.example.app;

import com.example.app.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Ant"));
    }
}
```

Trong `GreetingService.java`:

```java
package com.example.app.service;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Source root là `src`. Từ gốc đó, đường dẫn `com/example/app/Main.java` tương ứng với package `com.example.app`; đường dẫn `com/example/app/service/GreetingService.java` tương ứng với package `com.example.app.service`.

Khai báo `srcdir="src"` giúp Ant tìm các tệp nguồn trong cây thư mục này. Nếu đặt `srcdir` trực tiếp thành `src/com/example/app`, Ant sẽ xem thư mục đó là gốc mới; cách đặt này có thể làm việc tìm kiếm package con hoặc source phụ thuộc không còn phù hợp với cấu trúc dự án.

## 3. Package quyết định tên đầy đủ của lớp

Trong Java, package được xác định bởi câu lệnh `package` ở đầu tệp nguồn. Ví dụ:

```java
package com.example.app.service;

public class GreetingService {
}
```

Tên đầy đủ của lớp (*fully qualified class name*) là `com.example.app.service.GreetingService`. Dấu chấm trong tên package tương ứng với các cấp thư mục khi lưu source và class file theo cấu trúc package chuẩn:

```text
com.example.app.service.GreetingService
                 ↓
com/example/app/service/GreetingService.java
```

Java compiler dùng khai báo package để xác định tên lớp. Cây thư mục nguồn nên phản ánh package để mã nguồn dễ tìm, để compiler tìm source phụ thuộc theo source path và để các công cụ build, IDE cùng tuân theo một cấu trúc nhất quán.

Nếu tệp không có khai báo `package`, lớp thuộc default package. Trong trường hợp đó, tệp nguồn thường nằm ngay dưới source root và class file được ghi ngay dưới `destdir`. Với ứng dụng thực tế, nên đặt lớp trong package có tên rõ ràng thay vì để lớp ứng dụng trong default package.

## 4. destdir là gốc của cây class output

`destdir` chỉ định thư mục gốc để compiler ghi các tệp `.class`. Các cấp package được tạo bên dưới thư mục này theo khai báo package của lớp.

Với cấu trúc nguồn ở trên và cấu hình:

```xml
<javac srcdir="src" destdir="build/classes" />
```

Kết quả dự kiến:

```text
project/
├── src/
│   └── com/example/app/
│       ├── Main.java
│       └── service/GreetingService.java
└── build/
    └── classes/
        └── com/example/app/
            ├── Main.class
            └── service/GreetingService.class
```

`build/classes` là classpath root cho các lớp vừa biên dịch. Khi chạy ứng dụng, JVM cần classpath trỏ tới `build/classes`, chứ không trỏ trực tiếp tới `build/classes/com/example/app`.

Ví dụ chạy lớp chính:

```shell
java -cp build/classes com.example.app.Main
```

Đường dẫn package được JVM suy ra từ tên lớp đầy đủ. Vì vậy, khi đóng gói JAR, nội dung trong `build/classes` thường được đưa vào archive sao cho các đường dẫn package vẫn được giữ nguyên.

## 5. Phân biệt srcdir, destdir và classpath

Ba cấu hình này có mục đích khác nhau và không thể thay thế cho nhau:

| Thuộc tính | Dùng để làm gì? | Ví dụ |
|---|---|---|
| `srcdir` | Tìm mã nguồn `.java` cần biên dịch | `src/main/java` |
| `destdir` | Ghi bytecode `.class` được biên dịch | `build/classes` |
| `classpath` | Cung cấp các lớp và thư viện mà mã nguồn tham chiếu khi biên dịch | `lib/api.jar` hoặc `build/classes` |

Ví dụ, một ứng dụng dùng thư viện bên ngoài `lib/greeting-api.jar`:

```xml
<path id="compile.classpath">
    <fileset dir="lib">
        <include name="*.jar" />
    </fileset>
</path>

<target name="compile">
    <mkdir dir="build/classes" />

    <javac
        srcdir="src"
        destdir="build/classes"
        classpathref="compile.classpath"
        includeantruntime="false"
        encoding="UTF-8" />
</target>
```

`classpathref` tham chiếu tới một Path đã khai báo bằng `id`. Có thể dùng nested element `<classpath>` thay cho `classpathref` nếu muốn đặt cấu hình ngay trong task:

```xml
<javac srcdir="src" destdir="build/classes" includeantruntime="false">
    <classpath>
        <fileset dir="lib">
            <include name="*.jar" />
        </fileset>
    </classpath>
</javac>
```

Nếu source code tham chiếu lớp trong một module đã biên dịch trước, thư mục output của module đó có thể được thêm vào classpath. Cần phân biệt source root với classpath: source root cung cấp mã `.java`; classpath cung cấp các lớp hoặc thư viện mà compiler cần tìm để giải quyết tham chiếu.

## 6. Biên dịch từ nhiều source root

Một dự án có thể chia mã nguồn thành nhiều source root, chẳng hạn mã chính, mã được sinh tự động hoặc mã bổ sung:

```text
project/
├── src/main/java/
├── src/generated/java/
└── build/classes/
```

Có thể truyền nhiều thư mục nguồn qua thuộc tính `srcdir` dạng path hoặc dùng nested element `<src>`:

```xml
<javac destdir="build/classes" includeantruntime="false">
    <src path="src/main/java" />
    <src path="src/generated/java" />
</javac>
```

Mỗi thư mục là một source root độc lập. Ví dụ, nếu `src/generated/java` có tệp `com/example/model/Customer.java` khai báo `package com.example.model;`, lớp được ghi dưới `build/classes/com/example/model/Customer.class` cùng với các lớp từ source root chính.

Khi có nhiều source root, cần tránh để cùng một lớp hoặc cùng một đường dẫn nguồn xuất hiện ở nhiều nơi. Nếu có hai tệp cùng khai báo một fully qualified class name, compiler có thể báo lỗi trùng lớp hoặc kết quả phụ thuộc vào cách các nguồn được đưa vào lần biên dịch.

## 7. Chọn tệp nguồn bằng includes và excludes

Task `javac` hỗ trợ các mẫu include và exclude để giới hạn những tệp nguồn được biên dịch. Mặc định, Ant tìm các tệp Java theo mẫu `**/*.java` trong source root.

Ví dụ bỏ qua mã thử nghiệm và mã được sinh tự động:

```xml
<javac
    srcdir="src"
    destdir="build/classes"
    includes="**/*.java"
    excludes="**/test/**,**/generated/**"
    includeantruntime="false" />
```

Các mẫu được đánh giá tương đối với source root. `*` khớp các ký tự trong một thành phần đường dẫn; `**` có thể đi qua nhiều cấp thư mục. Nếu có nhiều nhóm nguồn cần biên dịch với chính sách khác nhau, có thể tạo các target riêng hoặc dùng các nested source/path phù hợp.

Không nên loại bỏ tùy tiện một package chỉ vì tên thư mục của nó có từ `test` hoặc `generated`. Hãy đảm bảo mẫu loại trừ khớp với cấu trúc thực tế và không loại nhầm mã mà ứng dụng cần.

## 8. Encoding và tùy chọn biên dịch

Khi mã nguồn chứa tiếng Việt hoặc ký tự ngoài ASCII, thuộc tính `encoding` giúp compiler đọc tệp theo charset đã dùng khi lưu:

```xml
<javac
    srcdir="src"
    destdir="build/classes"
    encoding="UTF-8"
    includeantruntime="false" />
```

Nếu encoding không khớp, compiler có thể báo lỗi ký tự không hợp lệ hoặc diễn giải sai literal trong mã nguồn. Nên thống nhất UTF-8 cho source code và cấu hình `encoding="UTF-8"` rõ ràng trong buildfile.

Một số thuộc tính thường dùng khác:

| Thuộc tính | Ý nghĩa |
|---|---|
| `debug` | Yêu cầu tạo thông tin debug trong bytecode |
| `deprecation` | Hiển thị thông tin về việc sử dụng API deprecated |
| `nowarn` | Tắt các cảnh báo compiler theo hỗ trợ của compiler adapter |
| `source` | Phiên bản cú pháp/ngôn ngữ nguồn được chấp nhận |
| `target` | Phiên bản bytecode đích |
| `includeantruntime` | Có đưa thư viện runtime của Ant vào classpath biên dịch hay không |

Ví dụ cấu hình:

```xml
<javac
    srcdir="src"
    destdir="build/classes"
    encoding="UTF-8"
    debug="true"
    deprecation="true"
    source="17"
    target="17"
    includeantruntime="false" />
```

Các giá trị `source` và `target` phải phù hợp với JDK/compiler đang chạy và yêu cầu tương thích của ứng dụng. Với JDK hiện đại, cần xem xét cơ chế `--release` nếu muốn ràng buộc cả phiên bản ngôn ngữ lẫn API nền tảng; khả năng truyền tùy chọn này phụ thuộc phiên bản Ant và compiler adapter. Không nên giả định `source`/`target` tự giới hạn toàn bộ API của JDK mới.

## 9. Ví dụ buildfile hoàn chỉnh

Ví dụ dưới đây biên dịch mã nguồn chính và mã nguồn sinh tự động vào cùng một thư mục class output. Các thư viện JAR trong `lib` được đưa vào classpath.

```xml
<project name="javac-package-example" default="compile">

    <property name="main.src" value="src/main/java" />
    <property name="generated.src" value="src/generated/java" />
    <property name="classes.dir" value="build/classes" />

    <path id="compile.classpath">
        <fileset dir="lib">
            <include name="*.jar" />
        </fileset>
    </path>

    <target name="clean">
        <delete dir="build" />
    </target>

    <target name="compile" depends="clean">
        <mkdir dir="${classes.dir}" />

        <javac
            destdir="${classes.dir}"
            encoding="UTF-8"
            debug="true"
            includeantruntime="false">

            <src path="${main.src}" />
            <src path="${generated.src}" />
            <classpath refid="compile.classpath" />
        </javac>
    </target>

</project>
```

Giả sử cây nguồn là:

```text
src/main/java/com/example/app/Main.java
src/main/java/com/example/app/service/GreetingService.java
src/generated/java/com/example/model/Customer.java
```

Và package trong từng tệp tương ứng với đường dẫn:

```java
// Main.java
package com.example.app;

// GreetingService.java
package com.example.app.service;

// Customer.java
package com.example.model;
```

Sau khi chạy `ant compile`, cây class output có dạng:

```text
build/classes/
└── com/
    └── example/
        ├── app/
        │   ├── Main.class
        │   └── service/
        │       └── GreetingService.class
        └── model/
            └── Customer.class
```

Hai source root được biên dịch vào cùng một `destdir`. Cấu trúc package được bảo toàn, do đó ứng dụng có thể chạy với `build/classes` làm classpath root.

## 10. Biên dịch tăng dần và clean output

Task `javac` của Ant có thể tránh biên dịch lại các tệp nguồn mà class tương ứng được xem là mới hơn. Việc so sánh dựa trên thông tin tệp và quy tắc biên dịch của task/compiler adapter. Đây là cơ chế incremental cơ bản, không phải hệ thống phân tích phụ thuộc hoàn chỉnh như một số build tool hiện đại.

Nếu thay đổi classpath, phiên bản compiler hoặc cấu hình biên dịch, các class cũ có thể không còn phản ánh chính xác cấu hình mới. Trong trường hợp đó, một target `clean` xóa output cũ trước khi biên dịch giúp tránh giữ lại bytecode lỗi thời.

```xml
<target name="clean-classes">
    <delete dir="build/classes" />
</target>

<target name="compile-clean" depends="clean-classes">
    <mkdir dir="build/classes" />
    <javac
        srcdir="src/main/java"
        destdir="build/classes"
        encoding="UTF-8"
        includeantruntime="false" />
</target>
```

Không nhất thiết phải clean trước mọi lần compile nếu incremental build là yêu cầu. Có thể giữ hai target riêng: `compile` để biên dịch thường ngày và `compile-clean` để buộc tạo lại toàn bộ class output khi thay đổi cấu hình hoặc cần kiểm tra bản build sạch.

## 11. Lỗi thường gặp khi cấu hình javac

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant không tìm thấy tệp nguồn | `srcdir` trỏ sai source root hoặc include loại bỏ tệp | Kiểm tra thư mục nguồn, mẫu include/exclude và cấu trúc thư mục |
| Không tìm thấy package hoặc lớp được import | Thiếu thư viện trên classpath hoặc thiếu source root cần thiết | Kiểm tra `classpath`, nested `src` và dependency biên dịch |
| Class file nằm cạnh source | Không cấu hình `destdir` | Chỉ định thư mục output riêng và tạo thư mục trước khi biên dịch |
| Không tìm thấy lớp khi chạy ứng dụng | Dùng sai classpath root, trỏ vào thư mục package con thay vì gốc output | Đặt classpath là `destdir`, ví dụ `build/classes` |
| Tệp class nằm trong package không như dự kiến | Khai báo `package` trong source không khớp với cấu trúc mong muốn | Kiểm tra package statement và cây thư mục tương ứng |
| Ký tự tiếng Việt bị lỗi hoặc compiler báo ký tự không hợp lệ | Encoding nguồn không khớp encoding compiler dùng | Khai báo `encoding` đúng với source, thường là UTF-8 |
| Ant đưa các lớp không mong muốn vào classpath | Runtime của Ant được tự động thêm vào classpath biên dịch | Đặt `includeantruntime="false"` và khai báo dependency cần thiết tường minh |
| Kết quả còn class cũ sau khi đổi package hoặc xóa source | Incremental compile không xóa mọi output lỗi thời | Chạy target clean trước khi biên dịch lại |
| Lỗi phiên bản Java không tương thích | `source`/`target` hoặc JDK compiler không phù hợp | Đồng bộ phiên bản JDK và cấu hình biên dịch; xem xét `--release` khi cần |

Khi xử lý lỗi, hãy kiểm tra theo thứ tự: source root, package statement, classpath, destdir, encoding và phiên bản compiler. Cách này giúp xác định lỗi thuộc bước tìm nguồn, phân giải dependency hay ghi bytecode.

## 12. Quy trình tổ chức srcdir, destdir và package

Khi cấu hình biên dịch cho một dự án Java bằng Ant, có thể thực hiện theo trình tự sau:

1. Xác định một hoặc nhiều source root, thường là `src/main/java` và `src/generated/java`.
2. Bảo đảm các tệp Java khai báo package phù hợp với cấu trúc thư mục bên dưới source root.
3. Chọn một `destdir` riêng, chẳng hạn `build/classes`, làm classpath root của kết quả biên dịch.
4. Khai báo classpath cho các thư viện và module mà mã nguồn tham chiếu.
5. Đặt encoding và các tùy chọn compiler phù hợp với JDK mục tiêu.
6. Giới hạn nguồn bằng include/exclude khi dự án có nhiều nhóm mã khác nhau.
7. Tách target clean khỏi target compile để có thể chọn giữa incremental build và biên dịch sạch.
8. Kiểm tra cây class output và chạy lớp chính bằng classpath root để xác nhận package được giữ đúng.

`srcdir` xác định nơi Ant tìm mã nguồn; package statement xác định tên đầy đủ của lớp; `destdir` xác định gốc lưu bytecode theo cấu trúc package. Khi ba phần này nhất quán, các task tiếp theo có thể dùng thư mục class output để chạy ứng dụng hoặc đóng gói JAR một cách rõ ràng.
