# Output directory khi biên dịch bằng javac

**Output directory** là thư mục đích mà trình biên dịch Java dùng để ghi các tệp đầu ra. Với lệnh **javac**, tùy chọn **-d** chỉ định nơi lưu các tệp bytecode **.class** sau khi biên dịch. Tách mã nguồn và bytecode vào hai thư mục riêng giúp dự án dễ chạy, đóng gói, kiểm thử và dọn dẹp hơn.

Ví dụ:

~~~bash
javac -d build/classes src/com/example/Main.java
~~~

Lệnh này biên dịch mã nguồn và ghi các tệp class vào build/classes. Nếu lớp thuộc package com.example, javac tạo cấu trúc thư mục tương ứng bên dưới output directory:

~~~text
build/
└── classes/
    └── com/
        └── example/
            └── Main.class
~~~

Thư mục build/classes phải tồn tại trước khi chạy javac; trình biên dịch không tự tạo thư mục đích gốc. Các thư mục con tương ứng với package được tạo bên trong thư mục đích khi cần.

## 1. Tùy chọn -d của javac

Cú pháp:

~~~bash
javac -d <directory> <source-files>
~~~

Trong đó:

- **-d** là tùy chọn chỉ định thư mục đích.
- **directory** là đường dẫn output directory.
- **source-files** là một hoặc nhiều tệp .java cần biên dịch.

Ví dụ:

~~~bash
mkdir -p build/classes
javac -d build/classes src/com/example/Main.java
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
javac -d "build/classes" "src/com/example/Main.java"
~~~

Nếu đường dẫn có dấu cách, hãy đặt đường dẫn trong dấu nháy để shell truyền nó thành một đối số duy nhất.

Khi không chỉ định -d, javac ghi các tệp class cạnh tệp nguồn tương ứng theo cách biên dịch thông thường. Điều này có thể làm lẫn mã nguồn và bytecode, đặc biệt khi dự án có nhiều package hoặc nhiều lần biên dịch. Chỉ định output directory giúp đầu ra tập trung và dễ quản lý.

## 2. Cấu trúc package trong output directory

Đường dẫn thư mục đích được kết hợp với tên package khai báo trong mã nguồn. Ví dụ tệp src/com/example/app/Main.java:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from javac.");
    }
}
~~~

Biên dịch:

~~~bash
mkdir -p out
javac -d out src/com/example/app/Main.java
~~~

Kết quả:

~~~text
out/
└── com/
    └── example/
        └── app/
            └── Main.class
~~~

Tệp nguồn khai báo package com.example.app, vì vậy class được đặt tại out/com/example/app/Main.class. Tên package quyết định cấu trúc thư mục đầu ra; javac không lấy tên thư mục nguồn làm quy tắc duy nhất.

Nếu lớp không khai báo package (default package), tệp class được ghi trực tiếp vào output directory:

~~~text
out/
└── Main.class
~~~

Trong dự án thực tế, nên đặt lớp vào package có tên rõ ràng thay vì dùng default package. Package giúp tránh trùng tên lớp, tổ chức mã nguồn và xác định tên đầy đủ khi chạy chương trình.

## 3. Biên dịch nhiều tệp nguồn vào cùng một thư mục

Một chương trình thường có nhiều lớp nằm ở các package khác nhau. Ví dụ cấu trúc:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           ├── app/
│           │   └── Main.java
│           └── util/
│               └── Greeting.java
└── build/
    └── classes/
~~~

Tệp Greeting.java:

~~~java
package com.example.util;

public class Greeting {
    public static String message() {
        return "Hello from the output directory.";
    }
}
~~~

Tệp Main.java:

~~~java
package com.example.app;

import com.example.util.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Tạo output directory rồi biên dịch cả hai tệp:

~~~bash
mkdir -p build/classes
javac --release 17 -d build/classes \
    src/com/example/util/Greeting.java \
    src/com/example/app/Main.java
~~~

Trên PowerShell, có thể viết lệnh trên một dòng:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
javac --release 17 -d "build/classes" "src/com/example/util/Greeting.java" "src/com/example/app/Main.java"
~~~

Cả hai lớp được ghi vào cùng output directory nhưng vẫn nằm trong các thư mục package riêng:

~~~text
build/classes/
└── com/
    └── example/
        ├── app/
        │   └── Main.class
        └── util/
            └── Greeting.class
~~~

Có thể truyền nhiều tệp .java trong cùng một lần gọi javac. Trình biên dịch phân tích quan hệ giữa các lớp trong tập nguồn và tạo bytecode tương ứng. Đây thường là cách rõ ràng nhất cho ví dụ nhỏ hoặc script biên dịch đơn giản.

## 4. Kết hợp -d với -sourcepath

**-sourcepath** chỉ định nơi javac tìm các tệp nguồn bổ sung khi cần biên dịch các lớp được tham chiếu nhưng chưa được truyền trực tiếp trên dòng lệnh. Nó khác với **-d**:

- **-sourcepath**: nơi tìm mã nguồn .java.
- **-d**: nơi ghi bytecode .class.

Với cấu trúc src/com/example/app/Main.java và src/com/example/util/Greeting.java ở phần trước, có thể chỉ truyền Main.java:

~~~bash
mkdir -p build/classes
javac --release 17 -sourcepath src -d build/classes \
    src/com/example/app/Main.java
~~~

Khi Main tham chiếu com.example.util.Greeting, javac tìm nguồn tương ứng bên dưới src và có thể biên dịch lớp đó theo nhu cầu.

Đường dẫn sourcepath là gốc tìm kiếm package. Với package com.example.util, javac tìm tệp tương ứng theo cấu trúc com/example/util/Greeting.java bên dưới mỗi gốc sourcepath.

Có thể có nhiều thư mục nguồn, phân tách bằng dấu phân cách classpath của hệ điều hành:

~~~bash
javac -sourcepath "src:generated-src" -d build/classes src/com/example/app/Main.java
~~~

Trên Windows, dấu phân cách giữa các phần tử classpath là dấu chấm phẩy:

~~~powershell
javac -sourcepath "src;generated-src" -d "build/classes" "src/com/example/app/Main.java"
~~~

Khi viết script dùng nhiều hệ điều hành, cần chú ý khác biệt dấu phân cách đường dẫn và quy tắc quoting của shell. Nếu muốn lệnh dễ đọc và ít phụ thuộc shell, có thể liệt kê tường minh các tệp nguồn hoặc dùng argument file.

## 5. Phân biệt -d, -cp và -sourcepath

Ba tùy chọn này giải quyết ba nhiệm vụ khác nhau:

| Tùy chọn | Chức năng | Ví dụ |
|---|---|---|
| **-d** | Ghi các tệp class vào thư mục đích | -d build/classes |
| **-cp** hoặc **-classpath** | Tìm class hoặc JAR phụ thuộc khi biên dịch/chạy | -cp libs/library.jar |
| **-sourcepath** | Tìm tệp nguồn Java khi javac cần biên dịch bổ sung | -sourcepath src |

Ví dụ dự án sử dụng thư viện bên ngoài:

~~~bash
javac --release 17 -cp "libs/example.jar" -d build/classes src/com/example/Main.java
~~~

Javac đọc thư viện từ classpath, đọc nguồn từ đường dẫn được truyền, rồi ghi class vào build/classes.

Một nhầm lẫn phổ biến là nghĩ rằng -d build/classes tự động đưa thư mục đó vào classpath khi chạy. Điều này không đúng. Khi chạy chương trình, phải chỉ định classpath riêng:

~~~bash
java -cp build/classes com.example.app.Main
~~~

Nếu cần cả thư viện ngoài:

~~~bash
java -cp "build/classes:libs/example.jar" com.example.app.Main
~~~

Trên Windows:

~~~powershell
java -cp "build/classes;libs/example.jar" com.example.app.Main
~~~

Class name khi chạy là tên đầy đủ gồm package, không phải đường dẫn tệp .class. Ví dụ com.example.app.Main tương ứng với build/classes/com/example/app/Main.class khi classpath root là build/classes.

## 6. Đặt tên và tổ chức output directory

Tên thư mục đầu ra không bị javac cố định. Dự án có thể dùng out, classes, build/classes hoặc tên khác. Điều quan trọng là mọi lệnh compile, run, test và package cùng tham chiếu đúng một nơi.

Một cấu trúc thường dùng:

~~~text
project/
├── src/
│   ├── main/
│   │   └── java/
│   └── test/
│       └── java/
├── build/
│   ├── classes/
│   │   ├── main/
│   │   └── test/
│   └── libs/
└── libs/
~~~

Với dự án dùng Gradle, output của mã nguồn chính thường nằm dưới build/classes/java/main; mã kiểm thử có output riêng. Với Maven, bytecode chính thường nằm ở target/classes và bytecode test ở target/test-classes. Đây là quy ước của build tool, không phải tên bắt buộc của tùy chọn javac.

Nếu tự tổ chức dự án, nên tách đầu ra của main và test:

~~~bash
mkdir -p build/classes/main build/classes/test
~~~

Biên dịch mã nguồn chính:

~~~bash
javac --release 17 -d build/classes/main src/main/java/com/example/Main.java
~~~

Biên dịch test khi đã có thư viện test và class chính trên classpath:

~~~bash
javac --release 17 -cp "build/classes/main:libs/junit.jar" \
    -d build/classes/test src/test/java/com/example/MainTest.java
~~~

Lệnh minh họa trên Unix-like shell. Trên Windows, thay dấu hai chấm trong classpath bằng dấu chấm phẩy và điều chỉnh đường dẫn nếu cần. Việc tách output giúp không trộn class test với artifact runtime.

## 7. Argument file cho danh sách nguồn dài

Khi có nhiều tệp nguồn hoặc command line quá dài, javac hỗ trợ argument file. Tệp này chứa các tùy chọn và tên nguồn để javac đọc như đối số dòng lệnh.

Ví dụ tạo sources.args:

~~~text
--release
17
-d
build/classes
src/com/example/util/Greeting.java
src/com/example/app/Main.java
~~~

Chạy:

~~~bash
mkdir -p build/classes
javac @sources.args
~~~

Có thể truyền nhiều argument file trong một lệnh. Các quy tắc quoting và escape trong argument file do javac định nghĩa; khi đường dẫn có khoảng trắng, cần tuân theo cú pháp của javac thay vì mặc định sao chép cú pháp của shell.

Argument file hữu ích khi dự án có hàng trăm nguồn hoặc script cần giữ danh sách nguồn dễ kiểm tra. Nếu file được sinh tự động, hãy bảo đảm encoding và đường dẫn tương thích với môi trường build.

## 8. Output directory trong chương trình dùng module

Với dự án Java Platform Module System, mã nguồn có thể chứa module-info.java. Khi biên dịch theo module, javac vẫn dùng -d để chỉ định gốc output. Khi biên dịch nhiều module từ module source path, đầu ra được phân chia theo module để tránh trộn các lớp của module khác nhau.

Một cấu trúc nguồn đơn giản:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/
        └── example/
            └── app/
                └── Main.java
~~~

module-info.java:

~~~java
module com.example.app {
}
~~~

Biên dịch module:

~~~bash
mkdir -p out
javac --release 17 --module-source-path src -d out \
    -m com.example.app
~~~

Với module source path dạng trên, output được tổ chức dưới thư mục module tương ứng. Khi triển khai module, các tùy chọn như --module-path và --module xác định nơi tìm module và module/lớp cần chạy. Cần đọc cấu trúc đầu ra thực tế và kiểm tra module-info.class sau khi biên dịch.

Đối với một module đơn giản, cũng có thể truyền trực tiếp module-info.java cùng các nguồn của module:

~~~bash
mkdir -p out
javac --release 17 -d out \
    src/com.example.app/module-info.java \
    src/com.example.app/com/example/app/Main.java
~~~

Không trộn tùy tiện đầu ra của các module vào cùng một package tree. Tên module, package được export và module path là các phần riêng của mô hình module.

## 9. Các thư mục đầu ra khác của javac

Tùy chọn -d chủ yếu dành cho class files. Một số loại đầu ra khác có tùy chọn riêng:

| Tùy chọn | Đầu ra |
|---|---|
| **-d directory** | Tệp .class |
| **-s directory** | Mã nguồn được tạo bởi annotation processor |
| **-h directory** | Header native được tạo cho JNI |
| **-proc:only** | Chỉ chạy annotation processing, không biên dịch class thông thường |
| **-proc:none** | Không chạy annotation processing |

Ví dụ với annotation processor:

~~~bash
mkdir -p build/classes build/generated-sources
javac -processorpath libs/processor.jar \
    -processor com.example.GenerateProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/com/example/Model.java
~~~

Ở đây, class output đi vào build/classes, còn source được processor sinh ra đi vào build/generated-sources. Không nên nhầm -s với -d: chúng phục vụ hai loại artifact khác nhau.

Ví dụ tạo JNI header:

~~~bash
mkdir -p build/classes build/headers
javac -h build/headers -d build/classes src/com/example/NativeBridge.java
~~~

Thư mục header chứa các tệp header được sinh ra nếu nguồn có khai báo native method phù hợp. Nếu không dùng annotation processor hoặc JNI, không cần tạo các thư mục này.

## 10. Dọn dẹp output directory và tránh class cũ

Javac ghi đè tệp class được tạo lại, nhưng không phải công cụ dọn dẹp toàn bộ output directory. Nếu xóa hoặc đổi tên một lớp nguồn, tệp .class cũ có thể còn tồn tại trong thư mục đầu ra.

Ví dụ trước đây có:

~~~text
src/com/example/OldService.java
~~~

Sau đó đổi tên hoặc xóa nguồn này nhưng vẫn dùng lại build/classes, tệp:

~~~text
build/classes/com/example/OldService.class
~~~

có thể vẫn còn từ lần compile trước. Tệp cũ có thể gây nhầm lẫn khi chạy, đóng gói JAR hoặc kiểm thử.

Với một lần build sạch, hãy dọn thư mục output rồi tạo lại:

~~~bash
rm -rf build/classes
mkdir -p build/classes
javac --release 17 -d build/classes src/com/example/Main.java
~~~

Trên PowerShell:

~~~powershell
if (Test-Path "build/classes") {
    Remove-Item -Recurse -Force "build/classes"
}
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
javac --release 17 -d "build/classes" "src/com/example/Main.java"
~~~

Chỉ xóa đúng thư mục build do dự án quản lý. Không dùng lệnh xóa rộng trên một đường dẫn chưa kiểm tra nếu thư mục đó còn chứa artifact cần giữ.

Trong build pipeline, nên có bước clean rõ ràng hoặc dùng build tool quản lý output. Điều này giúp tránh kết quả khác nhau giữa máy developer và CI do tệp class cũ còn sót.

## 11. Đóng gói output directory thành JAR

Sau khi biên dịch, thư mục output chứa bytecode và có thể được đóng gói thành JAR:

~~~bash
jar --create --file build/app.jar -C build/classes .
~~~

Tùy chọn -C chuyển thư mục làm việc của lệnh jar tới build/classes, sau đó dấu chấm đưa nội dung của thư mục đó vào archive. Package path được giữ nguyên trong JAR.

Nếu có Main-Class trong manifest, có thể tạo executable JAR. Tạo tệp manifest.mf:

~~~text
Main-Class: com.example.app.Main

~~~

Dòng trống cuối manifest là cần thiết để kết thúc phần header. Tạo JAR:

~~~bash
jar --create --file build/app.jar --manifest manifest.mf -C build/classes .
~~~

Chạy:

~~~bash
java -jar build/app.jar
~~~

JAR chỉ chứa các tệp đã có trong output directory tại thời điểm đóng gói. Nếu biên dịch thiếu class hoặc đặt output sai, JAR cũng sẽ thiếu nội dung tương ứng. Nếu ứng dụng phụ thuộc thư viện ngoài, cần đóng gói dependency hoặc cấu hình classpath/module path phù hợp; lệnh jar cơ bản không tự gom toàn bộ dependency.

## 12. Ví dụ thực hành hoàn chỉnh với Java 17+

Ví dụ gồm hai lớp ở hai package khác nhau để minh họa cách javac tạo package tree bên trong output directory.

Cấu trúc nguồn:

~~~text
output-demo/
└── src/
    └── com/
        └── example/
            ├── app/
            │   └── Main.java
            └── util/
                └── Greeting.java
~~~

Tạo src/com/example/util/Greeting.java:

~~~java
package com.example.util;

public class Greeting {
    public static String message() {
        return "Hello from javac output directory.";
    }
}
~~~

Tạo src/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.util.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Từ thư mục gốc output-demo, tạo output directory:

~~~bash
mkdir -p build/classes
~~~

Biên dịch cả hai lớp:

~~~bash
javac --release 17 -d build/classes \
    src/com/example/util/Greeting.java \
    src/com/example/app/Main.java
~~~

Sau khi biên dịch, cây thư mục:

~~~text
output-demo/
├── src/
│   └── com/
│       └── example/
│           ├── app/
│           │   └── Main.java
│           └── util/
│               └── Greeting.java
└── build/
    └── classes/
        └── com/
            └── example/
                ├── app/
                │   └── Main.class
                └── util/
                    └── Greeting.class
~~~

Chạy chương trình bằng output directory làm classpath root:

~~~bash
java -cp build/classes com.example.app.Main
~~~

Output chính xác:

~~~text
Hello from javac output directory.
~~~

Nếu nhận lỗi ClassNotFoundException hoặc Could not find or load main class, kiểm tra:

1. Đã chạy từ đúng thư mục gốc hoặc dùng đường dẫn output tuyệt đối chưa?
2. Classpath có trỏ đến build/classes không?
3. Tên lớp đầy đủ có đúng com.example.app.Main không?
4. File build/classes/com/example/app/Main.class có tồn tại không?
5. Lệnh compile có ghi vào đúng output directory không?

Nếu gặp package com.example.util does not exist, kiểm tra tệp Greeting.java có nằm trong tập nguồn compile hoặc có nằm dưới sourcepath đúng cấu trúc package không.

## 13. Lỗi thường gặp và cách xử lý

**Output directory chưa tồn tại**

Lỗi thường xảy ra khi truyền -d build/classes nhưng thư mục build/classes chưa được tạo. Hãy tạo thư mục trước khi chạy javac. Javac không tạo thư mục đích gốc.

**Nhầm -d với -cp**

-d quyết định nơi ghi class; -cp quyết định nơi tìm class/JAR. Sau khi compile, dùng java -cp <output-directory> để chạy.

**Package declaration không khớp kỳ vọng**

Output path được tạo theo package khai báo trong source. Hãy kiểm tra dòng package và tên đầy đủ của lớp khi chạy.

**Chạy bằng tên file thay vì tên lớp đầy đủ**

Với class đã compile và có package, chạy java -cp out com.example.Main, không chạy đường dẫn out/com/example/Main.class.

**Chỉ biên dịch lớp chính nhưng không tìm được lớp phụ**

Truyền các source file liên quan trực tiếp hoặc khai báo -sourcepath trỏ tới gốc cây mã nguồn.

**Dùng class cũ còn sót**

Xóa và tạo lại output directory trước clean build để loại bỏ class đã bị xóa hoặc đổi tên trong source.

**Đưa thư mục output vào JAR sai cấp**

Dùng jar -C build/classes . để đưa nội dung output directory vào archive. Nếu đóng gói cả thư mục build/classes từ cấp cha, JAR có thể chứa thêm đường dẫn build/classes/ khiến package path không còn ở gốc archive.

**Dùng cùng thư mục cho source và output**

Tách src và build/classes giúp kiểm soát artifact, tránh nhầm file và dễ dọn dẹp. Không để bytecode sinh ra bị coi là nguồn đầu vào của lần build sau.

## 14. Quy trình sử dụng output directory

Một quy trình javac đơn giản, có thể lặp lại:

1. Chọn output directory riêng cho từng loại mã nguồn, ví dụ build/classes.
2. Tạo thư mục đích trước khi compile.
3. Chọn Java release bằng --release nếu cần kiểm soát API và bytecode mục tiêu.
4. Truyền đầy đủ source files hoặc cấu hình -sourcepath.
5. Dùng -cp cho thư viện cần thiết trong quá trình biên dịch.
6. Kiểm tra package tree và class files được tạo.
7. Chạy bằng classpath trỏ tới output directory.
8. Clean output trước khi build lại nếu cần bảo đảm không còn class cũ.
9. Đóng gói nội dung output thành JAR khi cần phân phối.

Output directory là ranh giới giữa mã nguồn và bytecode đã biên dịch. Khi dùng javac -d nhất quán, package được ánh xạ thành cấu trúc thư mục rõ ràng, classpath khi chạy dễ xác định và quy trình build dễ tái lập hơn.
