# Biên dịch một mô-đun hoặc nhiều mô-đun liên quan

## 1. Tổng quan

Java Platform Module System (JPMS) cho phép javac biên dịch một named module, nhiều module có quan hệ phụ thuộc trong cùng một lượt, hoặc một module dựa trên các module đã được biên dịch trước.

Khi biên dịch theo mô-đun, cần phân biệt ba vị trí:

- **Module source path (`--module-source-path`)**: nơi chứa mã nguồn của các named module. Mỗi module có thư mục riêng, bên trong có `module-info.java` và các package.
- **Module path (`--module-path`)**: nơi javac tìm các module đã được biên dịch, chẳng hạn exploded module hoặc modular JAR.
- **Destination (`-d`)**: thư mục nhận các file `.class`. Khi biên dịch nhiều module, javac tạo thư mục output riêng cho từng module.

Một module có thể được biên dịch riêng nếu các dependency cần thiết đã có sẵn. Khi các module phụ thuộc nhau, có thể biên dịch chúng trong cùng một lệnh hoặc biên dịch dependency trước rồi đưa output lên module path.

Các ví dụ dưới đây dùng cú pháp JPMS hiện hành và mã nguồn tương thích Java 17 trở lên.

## 2. Cấu trúc source tree cho named module

Với tùy chọn `--module-source-path`, cách bố trí phổ biến là một thư mục con cho mỗi module:

~~~text
project/
└── src/
    ├── com.example.greeting/
    │   ├── module-info.java
    │   └── com/
    │       └── example/
    │           └── greeting/
    │               └── api/
    │                   └── Greeter.java
    └── com.example.app/
        ├── module-info.java
        └── com/
            └── example/
                └── app/
                    └── Main.java
~~~

Quy tắc cần nhớ:

- Tên thư mục module tương ứng với tên module khai báo trong `module-info.java`.
- `module-info.java` nằm ở gốc thư mục module, ngang cấp với các thư mục package.
- Không đặt `module-info.java` bên trong một package và không khai báo `package` trong file này.
- Các file Java thuộc package nằm theo cấu trúc thư mục của package.
- Mỗi named module có module descriptor riêng.

Ví dụ, file `src/com.example.greeting/module-info.java`:

~~~java
module com.example.greeting {
    exports com.example.greeting.api;
}
~~~

File `src/com.example.greeting/com/example/greeting/api/Greeter.java`:

~~~java
package com.example.greeting.api;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module ứng dụng có descriptor tại `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.greeting.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Java modules"));
    }
}
~~~

Ứng dụng yêu cầu module thư viện bằng `requires`. Thư viện export package API để module ứng dụng có thể đọc các kiểu public trong package đó.

## 3. Các tùy chọn javac cần biết

| Tùy chọn | Công dụng |
|---|---|
| `--module-source-path` | Chỉ định nơi chứa source tree của các named module |
| `--module-path` hoặc `-p` | Chỉ định nơi tìm các module đã biên dịch hoặc modular JAR |
| `--module` hoặc `-m` | Chọn một hoặc nhiều module cần biên dịch |
| `-d` | Chỉ định thư mục đầu ra chứa class file |
| `--release N` | Biên dịch theo API và quy tắc của Java release N |
| `-g` | Sinh thông tin debug trong class file |
| `-verbose` | Hiển thị thông tin chi tiết về các thao tác biên dịch |

Phân biệt các tùy chọn:

- `--module-source-path` trỏ tới mã nguồn của module.
- `--module-path` trỏ tới module đã biên dịch hoặc JAR có thể được dùng làm dependency.
- `-m` nhận tên module, không nhận tên package hay tên class.
- Có thể chỉ định nhiều module cho `-m`, phân tách bằng dấu phẩy.
- `-d` là thư mục gốc cho output; javac tự tạo thư mục con theo tên module.

Ví dụ tổng quát:

~~~bash
javac --module-source-path src -d out -m module.one,module.two
~~~

Javac tìm source module trong `src`, biên dịch các module được chọn và đặt kết quả dưới `out`.

## 4. Biên dịch một module

Khi chỉ cần biên dịch module thư viện `com.example.greeting`, dùng:

~~~bash
javac --module-source-path src -d out -m com.example.greeting
~~~

Lệnh này thực hiện các bước:

1. Đọc source tree trong `src`.
2. Xác định source module có tên `com.example.greeting`.
3. Đọc `module-info.java` để biết tên module và các directive.
4. Biên dịch các file Java thuộc module.
5. Ghi `module-info.class` và các class file vào thư mục module bên trong `out`.

Kết quả:

~~~text
out/
└── com.example.greeting/
    ├── module-info.class
    └── com/example/greeting/api/
        └── Greeter.class
~~~

Đây là output của một module thư viện. Vì module này không có main class nên không thể khởi chạy trực tiếp như một ứng dụng. Module sẽ được đưa lên module path khi biên dịch hoặc chạy module khác cần nó.

Nếu source module có phụ thuộc vào một module khác, dependency đó cũng phải có thể được tìm thấy trong quá trình biên dịch, thông qua module source path hoặc module path.

## 5. Biên dịch nhiều module liên quan trong một lần

Khi có cả module thư viện và module ứng dụng, có thể chỉ định hai module trong cùng lệnh:

~~~bash
javac --module-source-path src -d out -m com.example.greeting,com.example.app
~~~

Javac xử lý các module được chỉ định và quan hệ phụ thuộc giữa chúng. Trong ví dụ:

- `com.example.greeting` cung cấp API.
- `com.example.app` khai báo `requires com.example.greeting`.
- Cả hai module đều có source nằm dưới `src`.
- Kết quả của từng module được ghi vào thư mục riêng dưới `out`.

Cấu trúc output:

~~~text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Chạy ứng dụng:

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Hello, Java modules!
~~~

Việc liệt kê tường minh các module trong `-m` giúp người đọc build script biết chính xác những module nào được yêu cầu biên dịch trong lượt đó.

## 6. Biên dịch module ứng dụng và để javac tìm source dependency

Khi module ứng dụng khai báo `requires` tới một module khác và cả hai source module đều có mặt trong module source path, javac có thể tìm và biên dịch source dependency theo module graph.

Ví dụ, chỉ định module ứng dụng:

~~~bash
javac --module-source-path src -d out -m com.example.app
~~~

Nếu `com.example.app` khai báo:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

và `com.example.greeting` có source hợp lệ trong `src`, javac tìm module nguồn đó để đáp ứng dependency. Output có thể chứa cả hai module:

~~~text
out/
├── com.example.greeting/
└── com.example.app/
~~~

Cách này hữu ích khi muốn bắt đầu build từ module ứng dụng hoặc module gốc. Nếu muốn kiểm soát rõ danh sách module được yêu cầu biên dịch, có thể liệt kê tường minh nhiều module như ở phần trước.

## 7. Biên dịch theo từng giai đoạn với dependency đã build

Trong dự án lớn, thư viện thường được build trước, sau đó ứng dụng được biên dịch dựa trên output của thư viện.

### 7.1. Giai đoạn 1: biên dịch module thư viện

~~~bash
javac --module-source-path src -d lib-out -m com.example.greeting
~~~

Kết quả:

~~~text
lib-out/
└── com.example.greeting/
    ├── module-info.class
    └── com/example/greeting/api/Greeter.class
~~~

### 7.2. Giai đoạn 2: biên dịch module ứng dụng

Đưa output thư viện lên module path:

~~~bash
javac --module-path lib-out --module-source-path src -d app-out -m com.example.app
~~~

Javac đọc descriptor và class file trong `lib-out` để kiểm tra directive `requires` của ứng dụng, sau đó ghi kết quả ứng dụng vào `app-out`.

Kết quả:

~~~text
app-out/
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

### 7.3. Chạy ứng dụng với hai output directory

Trên Linux hoặc macOS, dấu phân cách các phần tử module path là dấu hai chấm:

~~~bash
java --module-path lib-out:app-out -m com.example.app/com.example.app.Main
~~~

Trên Windows PowerShell, dấu phân cách là dấu chấm phẩy:

~~~powershell
java --module-path "lib-out;app-out" -m com.example.app/com.example.app.Main
~~~

Kết quả ở cả hai hệ điều hành:

~~~text
Hello, Java modules!
~~~

Cách build theo từng giai đoạn hữu ích khi thư viện và ứng dụng thuộc các project hoặc pipeline build riêng. Khi dependency thay đổi, cần build lại module bị ảnh hưởng và bảo đảm runtime module path chứa đủ các module cần thiết.

## 8. Chọn cách biên dịch phù hợp

| Tình huống | Cách làm |
|---|---|
| Một module độc lập | Dùng `--module-source-path`, `-d` và `-m module.name` |
| Nhiều module có source cùng project | Dùng một lệnh `javac` và liệt kê module bằng `-m module.one,module.two` |
| Ứng dụng cần module nguồn khác | Đặt các source module trong module source path và chọn module ứng dụng làm root |
| Ứng dụng phụ thuộc module đã build | Đưa output dependency vào `--module-path` khi biên dịch ứng dụng |
| Dependency đã đóng gói thành modular JAR | Đưa JAR lên `--module-path` |
| Muốn build theo từng project/pipeline | Biên dịch dependency trước, sau đó biên dịch module tiêu thụ |
| Muốn chọn API Java đích | Thêm `--release 17` hoặc release phù hợp với môi trường triển khai |

Không cần đưa module nguồn và module đã biên dịch vào cùng một nơi nếu quy trình build đã tách rõ hai giai đoạn. Dùng source path cho mã nguồn và module path cho dependency đã biên dịch để tránh nhầm lẫn.

## 9. Dùng modular JAR làm dependency

Sau khi biên dịch module thư viện thành exploded module, có thể đóng gói nó thành modular JAR.

~~~bash
jar --create --file greeting.jar -C lib-out/com.example.greeting .
~~~

Thư mục `com.example.greeting` chứa `module-info.class` ở gốc, vì vậy file JAR tạo ra giữ module descriptor và có thể đặt trên module path.

Kiểm tra descriptor của JAR:

~~~bash
jar --describe-module --file greeting.jar
~~~

Biên dịch ứng dụng với JAR làm dependency:

~~~bash
javac --module-path greeting.jar --module-source-path src -d app-out -m com.example.app
~~~

Chạy ứng dụng trên Windows PowerShell:

~~~powershell
java --module-path "greeting.jar;app-out" -m com.example.app/com.example.app.Main
~~~

Trên Linux hoặc macOS, dùng `greeting.jar:app-out` làm giá trị module path.

Nếu JAR không có `module-info.class` và được đặt trên module path, JDK có thể xem nó là automatic module theo quy tắc đặt tên module. Với thư viện được thiết kế cho JPMS, modular JAR có descriptor tường minh giúp tên module và ranh giới API ổn định hơn.

## 10. Phân biệt classpath và module path khi biên dịch

Classpath và module path phục vụ hai mô hình phân giải khác nhau:

- **Classpath (`--class-path` hoặc `-cp`)**: dùng cho class và JAR trên classpath, thường thuộc unnamed module.
- **Module path (`--module-path` hoặc `-p`)**: dùng để tìm named module và automatic module.
- **Module source path (`--module-source-path`)**: dùng để tìm source tree của named module.

Với mã nguồn có `module-info.java`, hãy tổ chức source theo module và biên dịch bằng module source path. Dependency modular đã biên dịch nên được đặt trên module path.

Không nên đưa một dependency named module vào classpath rồi mong javac áp dụng các directive `requires` và `exports` của nó. Nếu dự án đang dùng classpath, việc chuyển sang JPMS cần thiết kế module descriptor và cấu hình build tương ứng.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `module not found` | Dependency không có trong module source path hoặc module path | Kiểm tra tên module và vị trí chứa source/JAR/output |
| `module ... not found, required by ...` | Descriptor khai báo requires tới module không được tìm thấy | Bổ sung dependency vào module path hoặc source path phù hợp |
| `package ... is not visible` | Module phụ thuộc không export package được import | Kiểm tra directive exports của module cung cấp API |
| `module ... does not read ...` | Module hiện tại thiếu quan hệ requires cần thiết | Khai báo dependency trong module-info.java |
| `module-info.java` không được tìm thấy | Cấu trúc thư mục không khớp với module source path | Kiểm tra thư mục gốc và tên module |
| Class file được ghi sai vị trí | Dùng sai output directory hoặc compile source như classpath thông thường | Dùng `-d` và `--module-source-path` nhất quán |
| Ứng dụng compile được nhưng chạy thiếu module | Runtime module path không chứa đủ dependency | Bổ sung output hoặc modular JAR vào `--module-path` khi chạy |
| Package nằm trong nhiều named module | Cấu trúc project tạo split package | Sắp xếp package để mỗi package thuộc một named module phù hợp |
| Nhầm tên module với tên package | `-m` nhận tên module, còn main class được chỉ định riêng khi chạy | Dùng tên trong `module-info.java` cho `-m`; dùng tên đầy đủ của main class sau dấu gạch chéo |

Khi gặp lỗi, kiểm tra lần lượt tên module, vị trí `module-info.java`, các directive requires/exports, source path, module path và output directory.

## 12. Kiểm tra kết quả build

Sau khi biên dịch, kiểm tra cấu trúc output:

~~~text
out/
├── com.example.greeting/
│   ├── module-info.class
│   └── com/example/greeting/api/Greeter.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Dùng `jar --describe-module` để kiểm tra tên và các directive của modular JAR:

~~~bash
jar --describe-module --file greeting.jar
~~~

Dùng `javap -v` để kiểm tra module descriptor ở dạng class file:

~~~bash
javap -v out/com.example.greeting/module-info.class
~~~

Khi xác minh một build, cần kiểm tra:

- Mỗi module có đúng một `module-info.class` ở gốc output.
- Các class file nằm dưới package tương ứng.
- Module ứng dụng có thể đọc các package được export bởi dependency.
- Module path lúc chạy có đầy đủ module bắt buộc.
- Lệnh chạy chọn đúng module và main class.
- Stdout của ứng dụng khớp với kết quả mong đợi.

## 13. Checklist thực hành

- Tạo thư mục source riêng cho từng named module.
- Đặt `module-info.java` tại gốc từng thư mục module.
- Xác định module nào cần biên dịch trong lượt build hiện tại.
- Dùng `--module-source-path` cho source module.
- Dùng `--module-path` cho dependency đã biên dịch hoặc modular JAR.
- Dùng `-m` để chọn một hoặc nhiều module.
- Dùng `-d` để đặt output vào thư mục build.
- Với module phụ thuộc nhau, biên dịch cùng lúc hoặc build dependency trước.
- Chạy ứng dụng bằng `java --module-path ... -m module/main-class`.
- Kiểm tra descriptor, output tree và kết quả chạy.

## Tài liệu tham khảo

- [Java Compiler — javac](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html) — tùy chọn biên dịch, module source path, module path và chọn module.
- [Java Archive Tool — jar](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html) — đóng gói và kiểm tra modular JAR.
- [Java Platform Module System](https://docs.oracle.com/javase/9/docs/api/java/lang/module/package-summary.html) — khái niệm và API module nền tảng.
