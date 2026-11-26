# Chẩn đoán lỗi thiếu nguồn, sai package, không tìm thấy lớp và lỗi biên dịch

## Mục tiêu

Từ JDK 22, lệnh `java` có thể khởi chạy chương trình gồm nhiều file nguồn Java mà không cần biên dịch thủ công từng file trước. Tính năng này được giới thiệu bởi JEP 458 – Launch Multi-File Source-Code Programs và là tính năng chính thức từ JDK 22.

Khi chạy ở source-file mode, launcher biên dịch file nguồn được chỉ định cùng những file nguồn khác mà chương trình cần, sau đó nạp các class đã biên dịch trong bộ nhớ và gọi entry point. Cơ chế này thuận tiện cho ví dụ, công cụ nhỏ và chương trình thử nghiệm. Khi có lỗi, cần xác định lỗi xảy ra ở bước tìm file nguồn, biên dịch, nạp class hay thực thi.

Bài học tập trung vào bốn nhóm sự cố:

- Không tìm thấy file nguồn được chỉ định hoặc file nguồn phụ thuộc.
- Đường dẫn thư mục không khớp với khai báo package.
- Không tìm thấy class hoặc thư viện ở thời điểm chạy.
- Lỗi biên dịch trong một hoặc nhiều file nguồn.

Các quy tắc source-file mode được hoàn thiện từ JDK 22 và vẫn áp dụng trên JDK hiện đại. Tài liệu hiện hành dùng trong bài là Java SE 27. Không cần bật preview cho tính năng chạy nguồn nhiều file.

Tại thời điểm biên soạn (25/11/2026), JDK 27 là feature release mới nhất và đã GA ngày 15/09/2026; JDK 25 là bản LTS mới nhất. Vì vậy, các hướng dẫn hiện hành trong bài được đối chiếu với launcher và compiler của Java SE 27.

## Trước tiên, phân biệt source-file mode và class mode

Hai lệnh sau có ý nghĩa khác nhau:

~~~bash
# Source-file mode: truyền đường dẫn tới file .java
java src/app/Main.java

# Class mode: truyền tên đầy đủ của class đã biên dịch
java -cp out app.Main
~~~

Ở source-file mode, launcher biên dịch mã nguồn vào bộ nhớ rồi chạy class đầu tiên được khai báo trong file nguồn được chỉ định. Ở class mode, launcher tìm file `.class` đã biên dịch theo tên class và classpath/module path.

File nguồn được chỉ định cần có một hoặc nhiều top-level class; class đầu tiên là class được launcher chọn để chạy và phải có entry point `main` hợp lệ. Để tương thích rộng giữa các phiên bản, ví dụ trong bài dùng dạng `public static void main(String[] args)`.

Nếu vô tình chạy `java app.Main` trong khi chưa có `app/Main.class` trên classpath, lỗi thường liên quan đến việc không tìm thấy main class. Đó không phải là lỗi tìm file nguồn phụ thuộc. Hãy kiểm tra lệnh đang dùng có truyền đường dẫn `.java` hay tên class.

Có thể kiểm tra JDK đang được dùng:

~~~bash
java --version
javac --version
~~~

Đảm bảo `java` và `javac` thuộc JDK mong muốn. Nếu hai lệnh trỏ tới các bản JDK khác nhau, kết quả biên dịch và chạy có thể không như dự kiến.

## Cấu trúc thư mục mẫu

Ví dụ có ba file nguồn thuộc ba package:

~~~text
project/
└── src/
    ├── app/
    │   └── Main.java
    ├── service/
    │   └── OrderService.java
    └── model/
        └── Order.java
~~~

`Main.java`:

~~~java
package app;

import service.OrderService;

public class Main {
    public static void main(String[] args) {
        OrderService service = new OrderService();
        System.out.println(service.summary());
    }
}
~~~

`OrderService.java`:

~~~java
package service;

import model.Order;

public class OrderService {
    public String summary() {
        Order order = new Order(42, "Lan");
        return "Order " + order.id() + " for " + order.customer();
    }
}
~~~

`Order.java`:

~~~java
package model;

public record Order(long id, String customer) {
}
~~~

Chạy lệnh từ thư mục `project`:

~~~bash
java src/app/Main.java
~~~

Launcher xác định package của class được chạy là `app`, từ đó suy ra source root là `src`. Các file nguồn phụ thuộc được tìm theo package bên dưới source root:

- `app.Main` → `src/app/Main.java`
- `service.OrderService` → `src/service/OrderService.java`
- `model.Order` → `src/model/Order.java`

Launcher có thể tự tìm và biên dịch các file nguồn cần thiết trong source tree này. Không cần liệt kê từng file phụ thuộc trong lệnh `java`.

## Cách phân loại lỗi trước khi sửa

Hãy xác định chương trình dừng ở giai đoạn nào:

| Dấu hiệu | Giai đoạn | Nơi cần kiểm tra |
|---|---|---|
| Không mở được file `.java` hoặc lệnh báo không tìm thấy main class | Chọn file nguồn / chọn chế độ chạy | Đường dẫn, thư mục hiện tại, phần mở rộng và cú pháp lệnh |
| `package ... does not exist`, `cannot find symbol`, `bad source file` | Biên dịch | Source root, package, tên file, file phụ thuộc và classpath |
| `ClassNotFoundException`, `NoClassDefFoundError` | Nạp class lúc chạy | Classpath, module path, thư viện bên ngoài và class loader |
| Stack trace từ code trong `main` | Thực thi ứng dụng | Dữ liệu đầu vào và logic chương trình |

Lỗi biên dịch xảy ra trước khi `main` được gọi. Vì vậy, nếu launcher in lỗi compiler và thoát với mã khác 0, hãy sửa mã nguồn hoặc cấu hình tìm kiếm trước khi điều tra logic chạy.

## Lỗi 1: Không tìm thấy file nguồn được chỉ định

### Nguyên nhân

Lệnh source-file mode nhận đường dẫn tới file nguồn. Đường dẫn tương đối được tính từ thư mục làm việc hiện tại của terminal. Những trường hợp thường gặp:

- Đang đứng ở thư mục khác với thư mục dự án.
- Gõ sai tên file hoặc tên thư mục.
- Sai chữ hoa/chữ thường trên hệ thống file phân biệt hoa thường.
- Đường dẫn có khoảng trắng nhưng không được đặt trong dấu ngoặc kép.
- Nhầm tên class với đường dẫn file nguồn.

Ví dụ, cấu trúc là:

~~~text
project/
└── src/
    └── app/
        └── Main.java
~~~

Nếu terminal đang ở `project`, lệnh đúng là:

~~~bash
java src/app/Main.java
~~~

Nếu terminal đang ở `project/src`, lệnh tương ứng là:

~~~bash
java app/Main.java
~~~

Nếu đường dẫn chứa khoảng trắng:

~~~bash
java "source files/app/Main.java"
~~~

### Cách xử lý

1. Kiểm tra thư mục hiện tại bằng `pwd` trên Linux/macOS hoặc `Get-Location` trên PowerShell.
2. Liệt kê file để xác nhận tên và vị trí thực tế.
3. Dùng đường dẫn tương đối từ thư mục hiện tại hoặc đường dẫn tuyệt đối.
4. Đặt đường dẫn trong dấu ngoặc kép nếu có khoảng trắng.
5. Kiểm tra file có phần mở rộng `.java` khi muốn launcher tự chọn source-file mode.

Có thể truyền `--source` để yêu cầu source-file mode khi file không có phần mở rộng `.java`:

~~~bash
java --source 27 scripts/run-task
~~~

Giá trị phiên bản phải được JDK đang chạy hỗ trợ. Tùy chọn này cũng đặt phiên bản ngôn ngữ và API nền tảng dùng để biên dịch. Với file `.java` thông thường, không cần thêm `--source` nếu không có yêu cầu chọn phiên bản cụ thể.

## Lỗi 2: Không tìm thấy file nguồn phụ thuộc

### Nguyên nhân

Source-file mode tự tìm file nguồn phụ thuộc trong source tree có root được suy ra từ package của file khởi chạy. Launcher không quét tùy ý toàn bộ ổ đĩa hoặc mọi thư mục trong dự án.

Ví dụ, `Main.java` có:

~~~java
package app;

import service.OrderService;
~~~

Nhưng file `OrderService.java` lại nằm ở:

~~~text
project/
└── src/
    ├── app/Main.java
    └── helpers/OrderService.java
~~~

Trong khi package khai báo trong file là `service`, launcher sẽ tìm nguồn theo package `service` dưới source root, tức `src/service/OrderService.java`. File ở `src/helpers` không khớp vị trí mong đợi.

Khi không tìm thấy kiểu được import, compiler có thể báo:

~~~text
error: package service does not exist
error: cannot find symbol
~~~

### Cách sửa

Sắp xếp file theo package:

~~~text
project/
└── src/
    ├── app/Main.java
    └── service/OrderService.java
~~~

Và bảo đảm đầu file khai báo đúng:

~~~java
package service;
~~~

Nếu phụ thuộc nằm trong một thư viện đã biên dịch, thêm thư viện vào classpath thay vì đặt nó vào source tree:

~~~bash
java --class-path "lib/*" src/app/Main.java
~~~

Các tùy chọn môi trường biên dịch như `--class-path` hoặc `--module-path` phải đặt trước file nguồn trên dòng lệnh. Những đối số sau tên file nguồn được chuyển cho chương trình.

## Lỗi 3: Package không khớp với thư mục

### Quy tắc

Tên package mô tả đường dẫn thư mục tương ứng từ source root. Ví dụ:

| Khai báo trong file | Đường dẫn mong đợi |
|---|---|
| `package app;` | `src/app/Main.java` |
| `package service;` | `src/service/OrderService.java` |
| `package com.example.model;` | `src/com/example/model/Order.java` |
| Không khai báo package | File nằm trực tiếp trong source root |

Với source-file mode, source root của file được chạy được suy ra từ package. Nếu `Main.java` khai báo `package app;`, vị trí thông thường là `src/app/Main.java`; source root là `src`.

### Ví dụ sai

~~~text
project/
└── src/
    ├── Main.java
    └── service/OrderService.java
~~~

Nhưng `Main.java` lại khai báo:

~~~java
package app;
~~~

Trong khi file phụ thuộc khai báo `package service;`. Vị trí file khởi chạy không khớp với package, nên source root được suy ra không như cấu trúc dự án dự định. Các package phụ thuộc có thể không được tìm thấy.

### Sửa đúng

~~~text
project/
└── src/
    ├── app/
    │   └── Main.java
    └── service/
        └── OrderService.java
~~~

Chạy từ `project`:

~~~bash
java src/app/Main.java
~~~

Lưu ý: launcher không áp dụng một số ràng buộc đặt tên file tùy chọn của JLS cho chính file nguồn được chỉ định để chạy. Tuy nhiên, việc sắp xếp đúng package và thư mục vẫn cần thiết để launcher suy ra source root và tìm các file phụ thuộc. Với các file phụ thuộc được compiler tự tìm, hãy giữ tên file và package nhất quán.

## Lỗi 4: Không tìm thấy class khi chạy

Không phải mọi lỗi “không tìm thấy class” đều là lỗi thiếu file nguồn. Cần phân biệt lỗi biên dịch với lỗi nạp class ở thời điểm chạy.

### Thiếu thư viện bên ngoài

Ví dụ, chương trình dùng một class trong thư viện bên thứ ba:

~~~java
import org.apache.commons.lang3.StringUtils;
~~~

Nếu thư viện không có trên classpath, compiler có thể báo:

~~~text
error: package org.apache.commons.lang3 does not exist
error: cannot find symbol
~~~

Đưa JAR vào classpath trước file nguồn:

~~~bash
java --class-path "lib/commons-lang3.jar" src/app/Main.java
~~~

Nếu có nhiều JAR trong thư mục `lib`, có thể dùng wildcard:

~~~bash
java --class-path "lib/*" src/app/Main.java
~~~

Trên Windows, dấu phân cách giữa nhiều mục classpath là dấu chấm phẩy (`;`); trên Linux/macOS là dấu hai chấm (`:`).

### ClassNotFoundException và NoClassDefFoundError

Hai lỗi thường gặp:

- `ClassNotFoundException`: thường xuất hiện khi chương trình chủ động tìm class bằng `Class.forName` hoặc một class loader, nhưng không tìm thấy class theo tên yêu cầu.
- `NoClassDefFoundError`: JVM cần nạp một class mà code đã tham chiếu, nhưng định nghĩa class không khả dụng trong quá trình chạy. Một nguyên nhân thường gặp là thiếu JAR trên runtime classpath.

Nếu lỗi xuất hiện sau khi `main` bắt đầu chạy, kiểm tra classpath/module path và cách nạp class. Nếu lỗi là `package does not exist` hoặc `cannot find symbol` trước khi chương trình chạy, kiểm tra cấu hình tìm kiếm lúc biên dịch.

### Giới hạn class loader trong source-file mode

Các class được biên dịch từ source tree được nạp bằng một class loader riêng, có ủy quyền cho application class loader. Vì vậy:

- Mã nguồn được launcher biên dịch có thể tham chiếu tới class trên application classpath.
- Class đã có trên application classpath không thể tham chiếu ngược tới class chỉ được khai báo trong source file đang chạy.
- Nếu application classpath đã chứa class cùng tên với class chính được chạy từ source file, đó là lỗi.

Nếu cần các class đã biên dịch và class từ source file tham chiếu lẫn nhau theo cách phức tạp, hãy biên dịch toàn bộ phần ứng dụng thành class file rồi chạy ở class mode.

## Lỗi 5: Lỗi biên dịch trong một file nguồn

Source-file mode vẫn thực hiện biên dịch trước khi chạy. Những lỗi cú pháp hoặc kiểu dữ liệu vẫn được compiler phát hiện.

Ví dụ:

~~~java
package app;

public class Main {
    public static void main(String[] args) {
        int total = "42";
        System.out.println(total);
    }
}
~~~

Compiler sẽ báo lỗi kiểu không tương thích vì không thể gán `String` cho `int`.

Các lỗi thường gặp:

| Thông báo thường gặp | Nguyên nhân | Hướng sửa |
|---|---|---|
| `';' expected` | Thiếu dấu chấm phẩy hoặc cú pháp chưa hoàn chỉnh | Kiểm tra dòng được chỉ ra và dòng ngay trước nó |
| `cannot find symbol` | Sai tên biến, method, class hoặc thiếu khai báo | Kiểm tra chính tả, import và file nguồn phụ thuộc |
| `package ... does not exist` | Package không tìm thấy trong source tree hoặc classpath | Kiểm tra package path và dependency |
| `incompatible types` | Kiểu dữ liệu không tương thích | Sửa kiểu hoặc chuyển đổi rõ ràng |
| `method ... cannot be applied` | Sai số lượng hoặc kiểu đối số | Đối chiếu chữ ký method |
| `bad source file` | File được tìm thấy nhưng không khai báo kiểu mà compiler đang tìm | Kiểm tra package và tên top-level type |
| `reached end of file while parsing` | Thiếu dấu ngoặc hoặc cấu trúc chưa đóng | Kiểm tra cặp `{}`, `()` và `[]` |

Không nên chỉ sửa dòng đầu tiên được báo lỗi. Một dấu ngoặc hoặc khai báo sai ở phía trên có thể tạo ra nhiều thông báo dây chuyền.

## Lỗi 6: Chọn sai phiên bản nguồn hoặc API

Có thể dùng `--source N` để chọn phiên bản ngôn ngữ và API nền tảng mà compiler dùng trong source-file mode:

~~~bash
java --source 27 src/app/Main.java
~~~

Nếu code dùng API chỉ có ở phiên bản mới hơn phiên bản được chọn, compiler có thể báo không tìm thấy method hoặc class dù JDK đang chạy có API đó. Hãy kiểm tra giá trị `N` được JDK hiện tại hỗ trợ và bảo đảm API cần dùng có từ phiên bản đó.

Nếu không cần cố định source release, có thể bỏ `--source` để dùng mặc định của JDK đang chạy.

Tính năng chạy chương trình nhiều file không phải preview feature. Không thêm `--enable-preview` chỉ để launcher tìm và biên dịch các file nguồn phụ thuộc.

## Lỗi 7: Chương trình cần annotation processing hoặc tùy chọn javac

Trong source-file mode, annotation processing bị tắt như thể dùng `-proc:none`. Launcher cũng không cung cấp cách truyền mọi tùy chọn riêng của compiler, chẳng hạn `-processor` hoặc `-Werror`.

Nếu dự án dựa vào annotation processor để sinh source hoặc class, ví dụ bộ sinh mapper, metamodel hay mã truy cập dữ liệu, source-file mode có thể không tạo được các kiểu mà chương trình cần.

Khi cần annotation processing hoặc kiểm soát đầy đủ tùy chọn biên dịch, chuyển sang dùng `javac` tường minh:

~~~bash
javac -d out --source-path src src/app/Main.java
~~~

Sau đó chạy class đã biên dịch:

~~~bash
java -cp out app.Main
~~~

Nếu cần thư viện bên ngoài:

~~~bash
javac -cp "lib/*" -d out --source-path src src/app/Main.java
java -cp "out;lib/*" app.Main
~~~

Lệnh thứ hai ở trên dùng dấu chấm phẩy theo cú pháp classpath của Windows. Trên Linux/macOS, thay bằng dấu hai chấm:

~~~bash
java -cp "out:lib/*" app.Main
~~~

Cách này cũng hữu ích khi cần giữ lại file `.class`, chỉ định thư mục output, bật lint, bật annotation processor hoặc kiểm tra chính xác quá trình biên dịch.

## Lỗi 8: Module và module path

Nếu source root chứa `module-info.java`, launcher dùng khai báo module đó để biên dịch các file nguồn trong source tree thành một named module. Nếu không có `module-info.java`, chúng được biên dịch trong unnamed module.

Khi dùng thư viện là named module, cần đưa module đó vào module path và bảo đảm module ứng dụng đọc module cần thiết:

~~~bash
java --module-path "mods" src/app/Main.java
~~~

Đây chỉ là dạng lệnh khung; module descriptor, tên module và các quan hệ `requires` phải được khai báo đúng. Nếu ứng dụng không cần module system, hãy giữ toàn bộ source tree trong unnamed module và dùng classpath cho thư viện classpath.

Dấu hiệu thường gặp khi module cấu hình sai là module không được tìm thấy, package không được export hoặc module không đọc module chứa kiểu đang tham chiếu. Trong trường hợp này, kiểm tra `module-info.java`, tên module, `requires`, `exports` và `--module-path`.

## Quy tắc thứ tự tùy chọn và đối số

Trong source-file mode, các tùy chọn liên quan đến môi trường biên dịch phải đặt trước tên file nguồn:

~~~bash
java --class-path "lib/*" src/app/Main.java input.txt
~~~

Ở đây:

- `--class-path "lib/*"` là tùy chọn của launcher, áp dụng cho biên dịch và môi trường chạy.
- `src/app/Main.java` là file nguồn được biên dịch và chạy.
- `input.txt` là đối số được chuyển vào chương trình.

Nếu đặt một tùy chọn sau tên file nguồn, launcher xem nó là đối số của ứng dụng, không phải tùy chọn biên dịch.

Source-file mode không hỗ trợ truyền mọi compiler option. Nếu cần `-processor`, `-Werror` hoặc cấu hình nâng cao của javac, hãy biên dịch tường minh bằng `javac`.

## Quy trình chẩn đoán theo từng bước

Khi một chương trình nhiều file không chạy được, có thể làm theo trình tự:

1. **Xác nhận JDK:** chạy `java --version` và `javac --version`; kiểm tra cả hai thuộc cùng JDK mong muốn.
2. **Xác nhận chế độ chạy:** dùng đường dẫn `.java` để chạy source-file mode; dùng tên class chỉ khi đã biên dịch.
3. **Xác nhận file chính:** kiểm tra đường dẫn file nguồn từ thư mục terminal hiện tại.
4. **Xác nhận package:** đối chiếu khai báo package với cấu trúc thư mục và source root.
5. **Xác nhận dependency nguồn:** bảo đảm các file `.java` phụ thuộc nằm trong source tree được suy ra.
6. **Xác nhận thư viện:** thêm JAR vào `--class-path` hoặc module vào `--module-path` trước file nguồn.
7. **Đọc lỗi compiler:** xử lý `package does not exist`, `cannot find symbol`, lỗi kiểu và lỗi cú pháp trước.
8. **Kiểm tra runtime lookup:** nếu biên dịch đã qua nhưng lỗi nạp class, kiểm tra classpath, module path, reflection và class loader.
9. **Chuyển sang javac khi cần:** dùng `javac -d out --source-path src ...` nếu cần annotation processing hoặc tùy chọn compiler đầy đủ.

## Khi nào nên dùng source-file mode, khi nào nên biên dịch tường minh?

| Tình huống | Cách phù hợp |
|---|---|
| Ví dụ nhỏ gồm vài file nguồn trong một source tree | `java path/to/Main.java` |
| Muốn thử nhanh một thay đổi mà không giữ output class | Source-file mode |
| Dự án dùng annotation processor | `javac` hoặc build tool |
| Cần `-Werror`, lint hoặc tùy chọn compiler chi tiết | `javac` |
| Cần kiểm soát output class và đóng gói artifact | `javac -d ...` và công cụ build |
| Ứng dụng có nhiều module hoặc quy trình build phức tạp | Module-aware compilation hoặc build tool |
| Class trên classpath cần tham chiếu ngược đến class ứng dụng | Biên dịch toàn bộ ứng dụng rồi chạy class mode |

Source-file mode là cách chạy và thử chương trình nhiều file thuận tiện. Khi quy trình cần khả năng tái lập build, annotation processing, đóng gói hoặc kiểm soát đầu ra, biên dịch tường minh vẫn là lựa chọn phù hợp.

## Tài liệu tham khảo

- [JEP 458 – Launch Multi-File Source-Code Programs](https://openjdk.org/jeps/458)
- [The java Command – Java SE 27, Source-File Mode](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [The javac Command – Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Launching a Multi-File Program – dev.java](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/)

