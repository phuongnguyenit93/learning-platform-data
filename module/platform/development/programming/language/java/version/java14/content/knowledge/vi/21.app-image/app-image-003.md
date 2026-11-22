# Chọn mô-đun cùng lớp khởi chạy của ứng dụng mô-đun khi tạo App Image

> **Java 14 → App image.** Trong Java 14, công cụ **`jpackage`** được giới thiệu ở trạng thái *incubating* (JEP 343); đến **Java 16 (JEP 392)**, `jpackage` trở thành công cụ chính thức. Vì vậy, bài học sử dụng **cú pháp `jpackage` hiện hành**, không hướng dẫn module `jdk.incubator.jpackage` hay quy trình cũ. Đề bài tập trung vào việc chỉ định **mô-đun chứa điểm vào** và **lớp `main`** khi tạo một **application image** bằng `--type app-image`, với lệnh Java/JDK 17+ và tài liệu JDK 25.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Java module**, **module path**, **main module**, **main class**, **application image** và **runtime image**.
2. Viết đúng lệnh `jpackage --type app-image --module-path <path> --module <module>/<main-class>` cho ứng dụng Java modular.
3. Biết khi nào có thể **bỏ phần `/main-class`**, khi nào phải **chỉ rõ lớp khởi chạy**.
4. Hiểu tại sao **`--main-class` đơn lẻ không phải cách khai báo main class của ứng dụng modular** với `jpackage`.
5. Tạo một dự án Java 17 gồm **hai mô-đun có `requires`/`exports`**, biên dịch, đóng gói modular JAR, chạy thử và tạo app image.
6. Kiểm tra tên mô-đun và điểm vào bằng `jar --describe-module` cùng `java --module-path ... --module ...` trước khi đóng gói.
7. Khởi chạy ứng dụng từ app image trên Linux, Windows và macOS; biết lý do **không build chéo native image/installer** cho OS khác.
8. Chẩn đoán lỗi thường gặp: sai module path, sai tên module, nhập nhầm tên package, thiếu `main`, thiếu dependency hoặc trộn hai chế độ modular/non-modular.
9. Áp dụng quy trình QA thực tế, tránh phụ thuộc tính năng incubating đã lỗi thời.

## 2. App image là gì, và khác “runtime image” ra sao?

Trong `jpackage`, **application image (app image)** là cây thư mục/ứng dụng đã được bố trí sẵn để chạy trên **hệ điều hành đích**, gồm launcher và Java runtime phù hợp. Nó được tạo bởi:

~~~bash
jpackage --type app-image ...
~~~

Đây là **mảnh câu lệnh**; dấu `...` biểu thị các tham số còn phải cung cấp, không phải lệnh thực thi hoàn chỉnh.

Những khái niệm dễ nhầm:

| Khái niệm | Ý nghĩa | Được chọn bằng |
| --- | --- | --- |
| **Named module** | Mô-đun có tên, khai báo trong `module-info.java`, ví dụ `org.acme.app` | Cấu trúc dự án, `module-info.java` |
| **Main module** | Mô-đun chứa điểm bắt đầu ứng dụng | `--module org.acme.app` |
| **Main class** | Lớp chứa phương thức khởi chạy, ví dụ `org.acme.app.Main` | Phần `/org.acme.app.Main` của `--module`, hoặc main class đã ghi trong modular JAR |
| **Module path** | Vị trí chứa modular JAR/mô-đun để công cụ tìm và phân giải dependency | `--module-path mlib` |
| **Runtime image** | Java runtime được `jlink` tạo để chạy tập mô-đun cần thiết | `jpackage` thường tạo tự động bằng `jlink`, hoặc dùng `--runtime-image` |
| **Application image** | Bundle chứa launcher, ứng dụng và runtime | `--type app-image` |
| **Native installer** | Gói cài đặt theo OS như `exe`, `msi`, `deb`, `rpm`, `pkg`, `dmg` | Kiểu `--type` khác `app-image` |

**App image không đồng nghĩa installer.** Tạo `--type app-image` cho phép bạn chạy thử bundle trước khi làm gói cài đặt. Lệnh này không tự tạo file `.msi` hay `.dmg`.

**Đừng nhầm `--type app-image` với `--app-image`.** `--type app-image` yêu cầu **tạo** app image mới; `--app-image <đường-dẫn>` là đầu vào **app image đã có** khi muốn xây dựng gói phân phối ở lượt `jpackage` tiếp theo. Bài này chủ yếu dùng dạng tạo mới.

## 3. Cú pháp chính xác để chọn mô-đun và lớp khởi chạy

Theo tài liệu `jpackage` hiện hành, phần quan trọng nhất là:

~~~text
--module-path <module-path>
--module <module-name>[/<fully-qualified-main-class>]
~~~

Trong đó:

- `--module-path`, viết ngắn `-p`: đường dẫn tới thư mục chứa module hoặc tới modular JAR. Đây là **nơi tìm**, **không phải tên main module**.
- `--module`, viết ngắn `-m`: nhận **tên mô-đun chính** và tùy chọn **tên lớp khởi chạy đầy đủ** sau ký tự `/`.
- Tên mô-đun ví dụ `org.acme.app` được lấy từ `module-info.java`, **không phải tên file JAR** và không phải tên thư mục chứa dự án.
- Lớp main ví dụ `org.acme.app.Main` là **fully qualified class name** (bao gồm package), **không phải** chỉ `Main` khi lớp thuộc package.

Lệnh hoàn chỉnh mẫu:

~~~bash
jpackage --type app-image --name ModularDemo --dest out --module-path mlib --module org.acme.app/org.acme.app.Main
~~~

Lệnh này nói với `jpackage`:

1. Tạo **app image**, không phải installer.
2. Đặt tên ứng dụng/launcher là `ModularDemo`.
3. Ghi kết quả vào thư mục `out`.
4. Tìm mô-đun trong thư mục `mlib`.
5. Dùng `org.acme.app` làm **main module**.
6. Gọi `org.acme.app.Main` làm **main class** khi launcher chạy.

Lệnh có thể dùng trên Linux/macOS và Windows trong terminal tương ứng nếu thư mục đầu vào đã được tạo và JDK có `jpackage`.

### So với lệnh `java`

Trước khi chạy `jpackage`, nên kiểm chứng cùng một điểm vào bằng:

~~~bash
java --module-path mlib --module org.acme.app/org.acme.app.Main
~~~

Cặp `--module-path`/`--module` có cùng cách chọn main module và main class. Nếu lệnh `java` còn chưa chạy được, nên sửa module graph/điểm vào **trước khi** thử đóng gói.

## 4. Đừng dùng nhầm `--main-class` của chế độ non-modular

Hai chế độ `jpackage` chọn điểm vào khác nhau:

| Ứng dụng | Cú pháp đúng | Điều cần tránh |
| --- | --- | --- |
| **Modular** (named module trong module path) | `--module-path mlib --module org.acme.app/org.acme.app.Main` | Đừng dùng `--main-class org.acme.app.Main` thay `/Main`. |
| **Modular, JAR đã ghi main class** | `--module-path mlib --module org.acme.app` | Chỉ bỏ `/Main` khi module thật sự khai báo điểm vào. |
| **Non-modular** (JAR classpath) | `--input input --main-jar app.jar --main-class org.acme.app.Main` | Không trộn `--main-jar` với `--module`. |

Tài liệu `jpackage` quy định **`--main-class` chỉ được dùng nếu có `--main-jar`**. `--main-jar` và `--module` là **hai lựa chọn loại trừ nhau**.

Đây là mảnh lệnh **cố ý sai với ứng dụng modular**:

~~~bash
jpackage --type app-image --name ModularDemo --module-path mlib --module org.acme.app --main-class org.acme.app.Main
~~~

Hãy thay bằng:

~~~bash
jpackage --type app-image --name ModularDemo --module-path mlib --module org.acme.app/org.acme.app.Main
~~~

Hoặc ghi sẵn main class trong **modular JAR**, rồi chỉ định `--module org.acme.app` như phần sau.

**Lưu ý quan trọng:** `--module-path` của ứng dụng named-module khác với `--input` của đóng gói JAR theo classpath. Với một ví dụ **thuần modular**, đưa modular JAR vào `mlib` và cung cấp `--module-path mlib`; không cần thêm `--input` chỉ để xác định entry point.

## 5. Điều kiện để một lớp làm điểm vào

Trong các ví dụ Java 17 của bài học, lớp main dùng dạng kinh điển, ổn định:

~~~java
package org.acme.app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
~~~

Đây là một **file `Main.java` hợp lệ khi đặt trong package phù hợp**, nhưng để chạy như named module vẫn cần `module-info.java` và bước compile/module path.

Những điều nên kiểm tra:

- Tên lớp đầy đủ là **`org.acme.app.Main`**, không chỉ `Main`.
- `main` được khai báo `public static void main(String[] args)`, là điểm vào phù hợp với Java 17.
- Main class phải **thuộc main module** mà `--module` chỉ tới.
- Với ví dụ đơn giản, package chứa `Main` **không cần `exports`** chỉ để Java launcher gọi `main`. Export là cơ chế API giữa mô-đun, không phải bước bắt buộc để chọn điểm vào.
- Nếu main module cần sử dụng API từ mô-đun khác, `module-info.java` phải có `requires` tương ứng; mô-đun thư viện phải `exports` package API cần truy cập.
- Dùng tên module từ `module-info.java` hoặc metadata của JAR, **không suy đoán theo tên JAR**: file có thể tên `desktop-1.0.jar` nhưng module là `org.acme.app`.

Không sử dụng các dạng điểm vào mới ở mức preview hoặc phụ thuộc phiên bản cao hơn để giải thích một quy trình build `--release 17`. Phương thức `public static void main(String[] args)` đủ rõ và chạy ổn định.

## 6. Ví dụ end-to-end: hai mô-đun, một main class

Ví dụ này dùng **hai named modules** để thấy rõ khái niệm **main module** khác **module thư viện**. Lệnh compile, modular JAR, `java --module` và `jpackage --type app-image` đã được kiểm chứng trên OpenJDK 21, với `--release 17`.

### 6.1. Cấu trúc thư mục nguồn

Tạo các file với cấu trúc:

~~~text
project/
└── src/
    ├── org.acme.message/
    │   ├── module-info.java
    │   └── org/
    │       └── acme/
    │           └── message/
    │               └── Texts.java
    └── org.acme.app/
        ├── module-info.java
        └── org/
            └── acme/
                └── app/
                    └── Main.java
~~~

Lưu ý đoạn trên là **cây thư mục**, không phải code cần biên dịch. Có hai file `module-info.java` vì có hai module. Mỗi thư mục module mang đúng tên khai báo của module để dùng với `--module-source-path src`.

### 6.2. Module thư viện: `org.acme.message`

Tệp **`src/org.acme.message/module-info.java`**:

~~~java
module org.acme.message {
    exports org.acme.message;
}
~~~

Tệp **`src/org.acme.message/org/acme/message/Texts.java`**:

~~~java
package org.acme.message;

public final class Texts {
    private Texts() {
    }

    public static String greeting() {
        return "Hello from modules";
    }
}
~~~

Tại sao `exports org.acme.message`? Vì module ứng dụng cần gọi `Texts.greeting()` từ **module khác**. Nếu không xuất package này, code bên module ứng dụng không thể sử dụng công khai lớp `Texts` theo module access rules.

### 6.3. Module ứng dụng: `org.acme.app`

Tệp **`src/org.acme.app/module-info.java`**:

~~~java
module org.acme.app {
    requires org.acme.message;
}
~~~

Tệp **`src/org.acme.app/org/acme/app/Main.java`**:

~~~java
package org.acme.app;

import org.acme.message.Texts;

public class Main {
    public static void main(String[] args) {
        System.out.println(Texts.greeting());
        System.out.println("args=" + args.length);
    }
}
~~~

Có **một main module** là `org.acme.app`, nhưng **hai module tham gia runtime**: `org.acme.app` và `org.acme.message`. Đó là điều bình thường: `--module` chọn **module khởi chạy**, không có nghĩa runtime chỉ chứa đúng một module.

`module org.acme.app { requires org.acme.message; }` tạo quan hệ phụ thuộc giữa các module; công cụ `jlink` sẽ phải phân giải cả mô-đun phụ thuộc khi đóng gói.

### 6.4. Biên dịch cả hai module

Từ thư mục `project`, chạy:

~~~bash
javac --release 17 --module-source-path src -d mods -m org.acme.message,org.acme.app
~~~

Giải thích:

- `--release 17`: dùng API/ngôn ngữ mục tiêu Java 17.
- `--module-source-path src`: nguồn được tổ chức theo thư mục tên module dưới `src`.
- `-d mods`: output class/module descriptor vào thư mục `mods`.
- `-m org.acme.message,org.acme.app`: yêu cầu compiler biên dịch hai module.
- Dấu phẩy phân cách **tên module** trong tham số javac; không phải dấu phân cách của filesystem path.

Sau bước biên dịch, kết quả điển hình:

~~~text
mods/
├── org.acme.message/
│   ├── module-info.class
│   └── org/acme/message/Texts.class
└── org.acme.app/
    ├── module-info.class
    └── org/acme/app/Main.class
~~~

Đó là các **mô-đun biên dịch dạng thư mục (exploded modules)**. Để đóng gói phân phối, bài này tạo **modular JAR** và đưa vào thư mục `mlib`.

### 6.5. Tạo modular JAR

Tạo thư mục `mlib` trước (bằng trình quản lý file hoặc lệnh thích hợp với OS). Sau đó:

~~~bash
jar --create --file mlib/org.acme.message.jar -C mods/org.acme.message .
jar --create --file mlib/org.acme.app.jar -C mods/org.acme.app .
~~~

Cả hai JAR chứa `module-info.class`, vì thế vẫn là **explicit named modules**. Hai dấu `.` cuối lệnh là thư mục nội dung cần đóng gói sau khi công cụ chuyển tới thư mục được chỉ định bởi `-C`.

**Tại sao không ghi sẵn main class ở bước này?** Để minh họa trường hợp `jpackage` phải được chỉ định **rõ ràng** bằng `--module org.acme.app/org.acme.app.Main`. Chúng ta sẽ xem biến thể ghi main class vào JAR ở phần 8.

**Lệnh `jar` không tự tạo thư mục `mlib` nếu thư mục cha chưa có.** Đây là bước chuẩn bị cụ thể, tránh nhầm với lỗi tên module.

### 6.6. Chạy thử trước khi đóng gói

~~~bash
java --module-path mlib --module org.acme.app/org.acme.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello from modules
args=0
~~~

Có thể thử truyền hai tham số:

~~~bash
java --module-path mlib --module org.acme.app/org.acme.app.Main first second
~~~

**Stdout chính xác:**

~~~text
Hello from modules
args=2
~~~

Giá trị `args.length` do Java launcher truyền qua tham số sau `--module`, nên đây là cách kiểm thử ý nghĩa của điểm vào mà không cần dùng các tùy chọn riêng của `jpackage`.

Nếu `java --module-path ... --module ...` đã báo thiếu module, thiếu dependency hoặc không tìm thấy main class, **đừng chuyển ngay sang jpackage**: cần sửa cấu trúc module/JAR trước.

### 6.7. Tạo application image bằng `jpackage`

Sau khi các JAR đã có trong `mlib`:

~~~bash
jpackage --type app-image --name ModularDemo --dest out --module-path mlib --module org.acme.app/org.acme.app.Main
~~~

Các cờ quyết định đề bài:

- `--module-path mlib`: module path chứa **cả app module và dependency module**.
- `--module org.acme.app/org.acme.app.Main`: chọn **đúng một main module và một main class**.
- `--type app-image`: tạo app image, không tạo installer.
- `--name ModularDemo`: tên app/launcher.
- `--dest out`: thư mục chứa kết quả.

Trong quá trình tạo app image, `jpackage` thường dùng **`jlink`** để tạo runtime phù hợp khi bạn **không** cung cấp `--runtime-image`. Runtime bao gồm main module và các dependency được giải quyết, không phải tự sao chép toàn bộ thư mục JDK bằng tay.

Khi thành công, công cụ tạo app image theo cấu trúc dành cho **OS đang build**.

### 6.8. Chạy thử launcher của app image

Với ví dụ đặt `--name ModularDemo --dest out`, launcher điển hình là:

**Linux:**

~~~bash
./out/ModularDemo/bin/ModularDemo
~~~

**Windows PowerShell** (nếu tạo image trên Windows):

~~~powershell
.\out\ModularDemo\ModularDemo.exe
~~~

**macOS** (nếu tạo image trên macOS):

~~~bash
./out/ModularDemo.app/Contents/MacOS/ModularDemo
~~~

**Stdout mong đợi của cùng chương trình, nếu chạy launcher trong môi trường console hiển thị stdout:**

~~~text
Hello from modules
args=0
~~~

Trên Windows, launcher mặc định có thể không kết nối với console như một console application. Khi muốn kiểm thử chương trình in ra terminal, hãy **thêm `--win-console` vào lệnh `jpackage` chạy trên Windows**. Tùy chọn đó **chỉ dành cho Windows**; không thêm nó vào lệnh Linux/macOS.

Đường dẫn thực tế có thể khác chút ít theo quy ước nền tảng/phiên bản/tùy biến image; hãy **kiểm tra thư mục kết quả** nếu launcher không ở vị trí mong đợi. Quan trọng nhất là chạy **launcher trong app image**, không chỉ lặp lại `java --module` bằng JDK cài sẵn.

### 6.9. Bảng kiểm thử cho ví dụ

| Bước | Kết quả cần thấy |
| --- | --- |
| `javac --release 17 ...` | Không lỗi compile; hai thư mục module xuất hiện dưới `mods`. |
| `jar --create ...` | Hai modular JAR có `module-info.class` trong `mlib`. |
| `java --module-path mlib --module org.acme.app/org.acme.app.Main` | `Hello from modules` và `args=0`. |
| `jpackage --type app-image ...` | Image `ModularDemo` cho OS đang build được tạo. |
| Launcher trong app image | Cùng logic/đầu ra ứng dụng nếu console hiển thị stdout. |
| `java ... first second` | `args=2`, xác nhận main class nhận tham số. |

Đây là một dự án **tự chứa, không có dependency bên thứ ba** nên phù hợp làm ví dụ nền tảng về module/entry point. Với ứng dụng thật có JavaFX hoặc thư viện khác, module path và runtime dependencies sẽ cần cấu hình tương ứng.

## 7. Kiểm tra tên module và mô tả module trước khi chọn

Bạn không nên đoán main module từ tên file JAR. Công cụ `jar` có khả năng xem descriptor của một modular JAR:

~~~bash
jar --describe-module --file mlib/org.acme.app.jar
~~~

Ví dụ nội dung **có ý nghĩa** bạn sẽ thấy (thứ tự, vị trí dòng có thể thay đổi):

~~~text
org.acme.app
requires java.base mandated
requires org.acme.message
~~~

Điều quan trọng là xác định **`org.acme.app`** là tên module thật và có quan hệ `requires org.acme.message`. Dòng có thể chứa đường dẫn JAR hoặc metadata bổ sung; không coi block trên là stdout nguyên văn bắt buộc của mọi JDK.

Tương tự:

~~~bash
jar --describe-module --file mlib/org.acme.message.jar
~~~

Module thư viện sẽ có `exports org.acme.message` và không có nghĩa nó là **module khởi chạy**. Đường dẫn tới JAR thư viện vẫn nằm trên **module path**, nhưng `--module` phải chọn `org.acme.app`.

### Module path có thể có nhiều vị trí

Nếu dự án chia các module ra nhiều thư mục:

- Linux/macOS sử dụng dấu **`:`** trong một `--module-path` gồm nhiều đường dẫn.
- Windows sử dụng dấu **`;`**.
- Hoặc dùng **nhiều lần `--module-path`** theo tài liệu `jpackage`.

Ví dụ một danh sách path đơn giản trong một lệnh Linux/macOS:

~~~bash
jpackage --type app-image --name ModularDemo --module-path mlib:thirdparty --module org.acme.app/org.acme.app.Main
~~~

Mảnh này chỉ dùng trên hệ thống dùng dấu `:` làm path separator và giả định thư mục `thirdparty` tồn tại. Với Windows, thay bằng `mlib;thirdparty`, nhớ **đặt trong dấu nháy khi dùng PowerShell** để tránh `;` bị hiểu là dấu ngăn câu lệnh.

**Đơn giản hơn cho bài học:** đặt tất cả modular JAR vào `mlib` như ví dụ end-to-end, để không phải xử lý khác biệt của path separator.

## 8. Khi nào có thể bỏ `/main-class`?

Tài liệu `jpackage` cho phép:

~~~bash
jpackage --type app-image --name ModularDemo --module-path mlib --module org.acme.app
~~~

**Chỉ dùng khi main module đã chứa thông tin main class** trong descriptor của modular JAR (hoặc module có main class được xác định hợp lệ theo cơ chế tương ứng). Nếu main class **chưa được xác định**, hãy viết rõ `/org.acme.app.Main`.

### Cách đưa main class vào modular JAR hiện hành

Sau khi đã biên dịch lớp và `module-info.class`, có thể tạo lại JAR ứng dụng bằng `jar --main-class`:

~~~bash
jar --create --file mlib/org.acme.app.jar --main-class org.acme.app.Main -C mods/org.acme.app .
~~~

`jar --main-class` khi tạo **modular JAR** lưu thông tin điểm vào để các công cụ module biết lớp khởi chạy. Lúc này, kiểm tra:

~~~bash
jar --describe-module --file mlib/org.acme.app.jar
~~~

Trong phần mô tả module, bạn sẽ thấy thông tin có ý nghĩa như:

~~~text
main-class org.acme.app.Main
~~~

Đây là **trích yếu dòng quan trọng**, không phải toàn bộ output của `jar --describe-module`.

Chạy không cần phần `/main-class`:

~~~bash
java --module-path mlib --module org.acme.app
~~~

**Stdout chính xác:**

~~~text
Hello from modules
args=0
~~~

Tương tự, có thể dùng:

~~~bash
jpackage --type app-image --name ModularDemoWithEntry --dest out2 --module-path mlib --module org.acme.app
~~~

Hai cách sau đều hợp lệ khi mô-đun có điểm vào:

- `--module org.acme.app/org.acme.app.Main`: **chỉ rõ** lớp main tại lệnh `jpackage`.
- `--module org.acme.app`: để công cụ lấy **main class đã ghi trong module**.

**Không cần ghi main class ở hai nơi** để bài học chạy được. Tuy nhiên chỉ định tường minh `/org.acme.app.Main` thường giúp reviewer hiểu rõ điểm vào và dễ rà lỗi khi dự án có nhiều lớp mang phương thức `main`.

### Một module có nhiều lớp `main` thì sao?

Giả sử cùng module có `org.acme.app.Main` và `org.acme.app.AdminTool`, cả hai có `public static void main(String[] args)`. `jpackage` không tự suy đoán “lớp đúng” từ số lượng lớp:

~~~bash
jpackage --type app-image --name AdminTool --module-path mlib --module org.acme.app/org.acme.app.AdminTool
~~~

Lệnh này yêu cầu launcher dùng `AdminTool`, **không phải `Main`**. Nếu đã lưu main class trong modular JAR, việc chỉ định `/AdminTool` sẽ chọn lớp được nêu tường minh cho launcher. Cần đảm bảo lớp tồn tại, thuộc đúng module và có phương thức khởi chạy hợp lệ.

## 9. Chọn sai: lỗi gì và sửa ở đâu?

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `Module org.acme.app not found` | `--module-path` không chứa module đó, trỏ sai thư mục hoặc JAR chưa build | Kiểm tra `mlib` và `jar --describe-module --file ...`; thử `java --module-path mlib --module ...`. |
| `Could not find or load main class` | Phần sau `/` sai package/class hoặc class không được đóng gói | Kiểm tra cấu trúc JAR và tên `package` thực tế. |
| Main class không được chỉ rõ | Dùng `--module org.acme.app` nhưng modular JAR chưa khai báo main class | Thêm `/org.acme.app.Main` hoặc tạo JAR với `jar --main-class`. |
| `Module org.acme.message not found` | Main module `requires` dependency nhưng module path thiếu module thư viện | Đưa modular JAR phụ thuộc vào module path. |
| Không truy cập được `Texts` từ module app | Thiếu `requires` hoặc `exports`, không phải lỗi `jpackage` | Sửa `module-info.java`, biên dịch lại. |
| Dùng `--main-class` với `--module` | Hai cơ chế chọn điểm vào khác nhau | Với modular app, dùng `--module module/mainClass`. |
| Dùng cùng lúc `--main-jar` và `--module` | Hai chế độ đóng gói loại trừ nhau | Chọn rõ modular hoặc non-modular. |
| Module path chứa source `.java` | `jpackage` cần mô-đun đã biên dịch/JAR hợp lệ | Biên dịch và tạo modular JAR trước. |
| Tên module và tên JAR không giống nhau | Đoán module từ tên file | Đọc `module-info.java` hoặc `jar --describe-module`. |
| Package của main không được `exports` | Thường **không phải lý do launcher không tìm main** | Export dành cho API giữa module; kiểm tra main class và descriptor thật. |
| Runtime thiếu module dùng qua reflection/service | Module chưa nằm trong dependency graph của `jlink` | Kiểm tra module/service dependencies, thêm `--add-modules` khi có lý do đúng. |
| File launcher chạy trên Linux nhưng không mở trên Windows | App image có cấu trúc/định dạng **phụ thuộc OS** | Build/kiểm thử app image riêng trên Windows. |
| Trên Windows chạy launcher không thấy stdout | Launcher mặc định là GUI, không có console attach | Tạo image trên Windows với `--win-console` nếu cần ứng dụng console. |
| `jpackage` không tồn tại | Đang dùng JRE tùy biến thay vì JDK phù hợp | Dùng JDK có công cụ `jpackage`, kiểm tra `jpackage --version`. |

Một nguyên tắc debug hiệu quả: **kiểm tra module graph và lệnh `java --module` trước**, sau đó mới kiểm tra `jpackage` và launcher của app image. Tránh sửa nhiều cờ ngẫu nhiên cùng lúc.

## 10. `jpackage`, `jlink` và tập mô-đun được đóng gói

Với một ứng dụng modular, khi **không** chỉ định `--runtime-image`, `jpackage` thường gọi `jlink` để tạo runtime phù hợp với module graph. Main module được chỉ định bởi `--module` sẽ là một trong các module được liên kết vào runtime; các module được `requires` sẽ được phân giải theo module graph.

Ví dụ của bài có:

~~~text
org.acme.app
    └── requires org.acme.message
            └── requires java.base (ngầm định)
~~~

Do đó **main module** là `org.acme.app`, nhưng nó cần cả `org.acme.message` và `java.base` để chạy.

### Khi cần thêm module không được suy ra trực tiếp

`jpackage` hỗ trợ `--add-modules module1,module2` để chuyển danh sách module bổ sung cho bước tạo runtime:

~~~bash
jpackage --type app-image --name ModularDemo --dest out --module-path mlib --module org.acme.app/org.acme.app.Main --add-modules java.logging
~~~

Đây là ví dụ cú pháp; với chính ví dụ `ModularDemo` ở trên **không cần** thêm `java.logging`. Chỉ thêm module khi dependency thực tế của ứng dụng yêu cầu (ví dụ dùng dịch vụ, reflection hay cơ chế tải module động) và đã kiểm tra bằng test.

**Đừng coi `--add-modules` là cách sửa main class sai.** Nó quyết định module bổ sung trong runtime, không thay đổi `org.acme.app.Main` thành lớp khác.

### Tự tạo runtime bằng `jlink`

Với trường hợp cần runtime được kiểm soát riêng, có thể dùng `jlink` trước rồi cung cấp `--runtime-image` cho `jpackage`. Cơ chế đó **khác** việc chọn main class và không cần trong bài end-to-end cơ bản. Hãy bắt đầu bằng `jpackage` tự tạo runtime, sau đó mới tối ưu khi có yêu cầu cụ thể.

**Lưu ý về hệ điều hành:** application image và native installer được đóng gói cho **OS nơi công cụ chạy**. Không dùng một image Linux như ứng dụng Windows; cần build trên từng OS đích, kèm JDK/toolchain phù hợp.

## 11. App image không phải file installer

Khi dùng `--type app-image`, kết quả dùng để **kiểm thử launcher và runtime được bundle**, chưa phải bộ cài native. Điều đó có ích vì:

- Có thể chạy thử ứng dụng bằng **launcher của bundle**, không dựa vào JDK trên máy developer.
- Có thể kiểm tra tài nguyên, dependency, JVM options và cấu trúc ứng dụng sau khi đóng gói.
- Có thể kiểm tra hành vi chạy trên từng OS trước khi tạo installer.
- Khi cần tùy biến image, tài liệu Oracle cho phép chỉnh sửa image rồi chạy `jpackage` lần nữa với `--app-image` để tạo installer.

Nhưng cần nhớ:

- Linux tạo cấu trúc launcher/ELF riêng của Linux; Windows tạo `.exe`; macOS tạo `.app`.
- `jpackage` **không hỗ trợ cross-platform packaging** từ một OS sang OS khác.
- Runtime trong app image do JDK dùng để build tạo ra; `--release 17` chỉ ràng buộc API/bytecode lúc compile, **không tự biến runtime được bundle thành Java 17**.
- Khi phát hành thật, cần kiểm thử trên OS/kiến trúc mục tiêu, kiểm tra bản quyền và dependency, và thực hiện ký/notarize/installer theo chính sách hiện hành. Đó là bước phân phối sau khi đã chọn main module/class đúng.

## 12. Checklist QA có thể dùng trong dự án

| Kiểm tra | Lệnh hoặc bằng chứng | Mục đích |
| --- | --- | --- |
| Có JDK và công cụ `jpackage`? | `java --version`, `javac --version`, `jpackage --version` | Không dùng JRE thiếu công cụ build. |
| Đúng mô-đun nguồn? | `module-info.java` khai báo `org.acme.app` | Không suy đoán theo file JAR. |
| Main class có phương thức đúng? | `public static void main(String[] args)` | Điểm vào tương thích Java 17. |
| Module graph hợp lệ? | `requires org.acme.message` và `exports org.acme.message` | App dùng được API thư viện. |
| Compile có thành công? | `javac --release 17 --module-source-path src ...` | Tạo module descriptor và class file đúng. |
| Modular JAR chứa module descriptor? | `jar --describe-module --file ...` | Phân biệt named module với JAR thường. |
| Lệnh Java modular chạy? | `java --module-path mlib --module org.acme.app/org.acme.app.Main` | Xác nhận module path + entry point trước packaging. |
| Chọn main module/class đúng? | `--module org.acme.app/org.acme.app.Main` | Không chọn nhầm module thư viện hoặc package. |
| Tạo đúng loại đầu ra? | `--type app-image` | Không bất ngờ tạo installer mặc định. |
| Launcher từ image chạy? | Chạy launcher trong `out` trên OS đích | Xác nhận chính bundle được tạo. |
| Thiếu dependency runtime? | Chạy các tính năng chính, quan sát module/service loading | Không chỉ kiểm tra `main` in Hello. |
| Windows console? | `--win-console` khi cần terminal | Tránh tưởng launcher không chạy vì stdout ẩn. |
| Cross-OS? | Build/test riêng Windows/Linux/macOS | App image là native theo OS. |
| An toàn phát hành? | Kiểm tra version/runtime, provenance, binary signing cần thiết | Không phân phối image chưa được xác minh. |

**Quan trọng:** việc `jpackage` trả exit code 0 mới chứng minh quá trình tạo image thành công ở mức công cụ. Một bài QA tốt vẫn phải **chạy launcher từ image** và kiểm tra logic ứng dụng.

## 13. Bài tập thực hành và đáp án

### Bài 1 — Chọn đúng module/class

Một dự án có:

~~~java
module org.acme.app {
    requires org.acme.message;
}
~~~

và lớp `package org.acme.app; public class Main` có phương thức `main`. Hãy viết cờ chọn entry point.

**Đáp án:** `--module org.acme.app/org.acme.app.Main`.

### Bài 2 — Sai ở đâu?

~~~bash
jpackage --type app-image --module-path mlib --module org.acme.app --main-class org.acme.app.Main
~~~

**Đáp án:** `--main-class` không được dùng thay phần lớp của `--module` trong chế độ modular. Viết `--module org.acme.app/org.acme.app.Main`.

### Bài 3 — Vì sao main module không phải module thư viện?

`org.acme.message` có class `Texts` để trả chuỗi nhưng **không có `main`**. `org.acme.app` chứa class `Main` và `requires org.acme.message`. Tại sao không chọn `--module org.acme.message`?

**Đáp án:** module thư viện không khai báo điểm vào mong muốn; module ứng dụng mới là nơi chứa `Main.main(String[])`. `--module` chọn **module khởi chạy**, còn `--module-path` cho phép phân giải cả ứng dụng và dependency.

### Bài 4 — Bỏ phần `/main-class`

Nếu tạo lại JAR ứng dụng bằng:

~~~bash
jar --create --file mlib/org.acme.app.jar --main-class org.acme.app.Main -C mods/org.acme.app .
~~~

hãy viết lệnh chạy và lệnh packaging không có `/main-class`.

**Đáp án:**

~~~bash
java --module-path mlib --module org.acme.app
jpackage --type app-image --name ModularDemoWithEntry --module-path mlib --module org.acme.app
~~~

### Bài 5 — Hai lớp có `main`

Một module chứa `org.acme.app.Main` và `org.acme.app.AdminTool`. Nếu muốn launcher dành cho công cụ quản trị, chọn:

~~~text
--module org.acme.app/org.acme.app.AdminTool
~~~

Không đặt tên ngắn `AdminTool` khi lớp thuộc package `org.acme.app`.

### Bài 6 — Windows không thấy stdout

Bạn tạo image thành công trên Windows, chạy `ModularDemo.exe` nhưng terminal không hiện output. Lý do khả dĩ và cách xử lý?

**Đáp án:** launcher mặc định có thể không phải console launcher. Dùng `--win-console` **khi build image trên Windows** nếu ứng dụng cần xuất console. Đồng thời kiểm tra mã thoát/log, không chỉ quan sát cửa sổ terminal.

### Bài 7 — Module dependency vắng mặt

`java --module-path mlib --module org.acme.app/org.acme.app.Main` báo không tìm thấy `org.acme.message`.

**Đáp án:** đảm bảo `mlib/org.acme.message.jar` được tạo từ module đã compile và nằm trong module path, rồi kiểm tra `module-info.java` bằng `jar --describe-module`. Không giải quyết bằng cách thay main module thành module thư viện.

### Bài 8 — Runtime build với JDK 25, bytecode target 17

`javac --release 17` tạo class tương thích Java 17, nhưng khi `jpackage` chạy bằng JDK 25 thì runtime trong app image thường do JDK 25 tạo. **Đừng** diễn giải `--release 17` là ép app image chứa JDK 17. Muốn kiểm soát phiên bản runtime phải chọn **JDK build** hoặc cung cấp runtime image theo quy trình được phê duyệt.

## 14. Các nguồn kỹ thuật còn áp dụng

1. [Oracle Java SE 25 — `jpackage` command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): cú pháp `--module module-name[/main-class]`, `--module-path`, `--type app-image` và việc `--main-class` chỉ dùng khi `--main-jar`.
2. [Oracle Java SE 25 — Basic Packaging](https://docs.oracle.com/en/java/javase/25/jpackage/basic-packaging.html): chọn main module/class trong ứng dụng modular, default package format, tạo runtime bằng `jlink`.
3. [Oracle Java SE 25 — Image and Runtime Modifications](https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html): tạo app image, kiểm thử/tùy biến rồi đóng gói installer.
4. [Oracle Java SE 25 — `java` launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `java --module-path ... --module module[/mainclass]`.
5. [Oracle Java SE 25 — `javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--module-source-path`, `--module`/`-m`, `--release`, biên dịch named modules.
6. [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ chính thức từ Java 16, sau hai lần incubation tại Java 14/15.
7. [Oracle JDK 16 Release Notes](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): thay module `jdk.incubator.jpackage` thành công cụ production `jdk.jpackage`, tránh tài liệu cũ.
8. [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html): cấu trúc app image trên Linux/macOS/Windows và yêu cầu build trên từng hệ điều hành đích.

**Ghi nhớ:** với ứng dụng modular, **`--module-path` cho biết nơi tìm các module**, còn **`--module moduleName[/fully.qualified.Main]` chọn mô-đun khởi chạy và lớp `main`**. Nếu modular JAR đã ghi main class, có thể bỏ phần `/mainClass`; nếu chưa, hãy chỉ rõ. Dùng `--type app-image` để tạo bundle có launcher/runtime, kiểm chứng bằng `java --module` trước và chạy launcher trong app image sau. Đây là cách dùng `jpackage` chính thức còn áp dụng, không sử dụng cơ chế incubating cũ.