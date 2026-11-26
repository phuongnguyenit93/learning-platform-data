# Kích hoạt mô-đun jdk.incubator.vector bằng --add-modules

Với một chương trình dùng Vector API và chạy trên classpath, cần thêm mô-đun ở cả bước biên dịch lẫn bước chạy:

```shell
javac --add-modules jdk.incubator.vector -d out VectorModuleDemo.java
java --add-modules jdk.incubator.vector -cp out VectorModuleDemo
```

Hai cờ có cùng nội dung nhưng tác động đến hai lần xử lý độc lập: `javac` cần thấy API để biên dịch; JVM cần giải quyết mô-đun để nạp và chạy các lớp liên quan. Việc biên dịch thành công không tự lưu tùy chọn khởi chạy vào tệp `.class`.

## 1. Vì sao cần thêm mô-đun?

Vector API thuộc mô-đun **`jdk.incubator.vector`**. Mô-đun này cung cấp API diễn đạt phép tính vector để runtime có thể ánh xạ sang lệnh SIMD phù hợp. Tài liệu [JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/module-summary.html) và [JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html) đều ghi nhận mô-đun này ở trạng thái incubating.

Bài học giữ lại cách sử dụng từ Java 22 còn áp dụng trong Java hiện đại: chỉ định rõ dependency mô-đun, đồng bộ môi trường biên dịch và chạy, phân biệt incubator với preview. Phần API của ví dụ được đối chiếu với JDK 27; không nên suy ra rằng mọi API hoặc tệp đã biên dịch đều tương thích giữa các bản JDK.

Khi chương trình không khai báo `module-info.java`, mã chạy trên classpath thuộc unnamed module. Để sử dụng Vector API trong trường hợp này, thêm `jdk.incubator.vector` vào tập mô-đun gốc cần giải quyết bằng:

```text
--add-modules jdk.incubator.vector
```

Dạng dùng dấu bằng cũng hợp lệ:

```text
--add-modules=jdk.incubator.vector
```

Đây là tùy chọn của hệ thống mô-đun. Nó không tải một thư viện qua mạng và không cài thêm thành phần vào JDK. Ý nghĩa thêm root module được mô tả trong [tài liệu javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

## 2. Kiểm tra JDK trước khi sửa mã

Trước tiên, xác định phiên bản công cụ đang dùng:

```shell
java --version
javac --version
```

Trên PowerShell, có thể kiểm tra đường dẫn hai lệnh:

```powershell
Get-Command java, javac | Select-Object Name, Source
```

Nếu `javac` thuộc một JDK còn `java` thuộc JDK khác, cấu hình tưởng đúng vẫn có thể thất bại. Trong IDE hoặc CI, JDK của project, compiler và tiến trình chạy cũng có thể được chọn riêng.

Tiếp theo, kiểm tra mô-đun có trong runtime đang gọi không:

```shell
java --describe-module jdk.incubator.vector
```

Hoặc lọc danh sách mô-đun trong PowerShell:

```powershell
java --list-modules | Select-String -SimpleMatch 'jdk.incubator.vector'
```

Tìm tên `jdk.incubator.vector`; phần phiên bản đi kèm phụ thuộc bản JDK cài đặt. Các tùy chọn liệt kê và mô tả mô-đun được giải thích trong [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

Nếu runtime rút gọn hoặc bản phân phối đang dùng không có mô-đun đó, `--add-modules` không tạo ra nó. Hãy chọn một JDK/runtime có thành phần cần thiết. Không chép các lớp nội bộ từ một JDK khác vào classpath để thay cho việc chọn đúng runtime.

## 3. Ví dụ nhỏ để xác nhận biên dịch và chạy

Tạo `VectorModuleDemo.java` với nội dung:

```java
import jdk.incubator.vector.IntVector;

public class VectorModuleDemo {
    public static void main(String[] args) {
        IntVector values = IntVector.broadcast(IntVector.SPECIES_PREFERRED, 7);
        IntVector result = values.add(5);

        System.out.println("module=" + IntVector.class.getModule().getName());
        System.out.println("ketQua=" + result.lane(0));
    }
}
```

Ví dụ tạo vector có giá trị 7 ở mỗi lane, cộng 5 vào mỗi lane rồi lấy lane đầu tiên. Các thao tác `broadcast`, `add` và `lane` thuộc [IntVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html).

Từ thư mục chứa tệp nguồn, biên dịch:

```shell
javac --add-modules jdk.incubator.vector -d out VectorModuleDemo.java
```

Sau đó chạy:

```shell
java --add-modules jdk.incubator.vector -cp out VectorModuleDemo
```

Kết quả ứng dụng mong đợi:

```text
module=jdk.incubator.vector
ketQua=12
```

Hai dòng xác nhận chương trình tham chiếu được lớp trong đúng mô-đun và thực hiện được phép tính. Đây là ví dụ xác nhận cấu hình; thời gian chạy của nó không chứng minh lợi ích hiệu năng SIMD.

`SPECIES_PREFERRED` giúp tránh việc cố định độ rộng vector không phù hợp máy đang chạy. Khả năng sinh mã vector phụ thuộc runtime, phần cứng và phép toán; xem [ghi chú hiệu năng của Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

### Cảnh báo incubator không đồng nghĩa biên dịch thất bại

Khi biên dịch hoặc chạy, có thể thấy cảnh báo về incubating module. Chẳng hạn, một thông báo chạy thường có dạng:

```text
WARNING: Using incubator modules: jdk.incubator.vector
```

Nội dung hoặc cách trình bày có thể khác giữa phiên bản công cụ. Thông báo này nhắc trạng thái API chưa chính thức ổn định, không tự chứng minh phép tính sai hoặc mô-đun chưa được thêm.

Nếu build dùng chính sách coi warning là lỗi, cần xem cấu hình đó riêng với vấn đề module resolution. `javac` có nhóm cảnh báo `incubating`, được mô tả trong [các tùy chọn compiler](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html).

## 4. Import, classpath và add-modules có vai trò khác nhau

Dòng mã:

```java
import jdk.incubator.vector.IntVector;
```

cho phép viết tên ngắn `IntVector` trong tệp nguồn. Nó không phải chỉ thị yêu cầu launcher thêm mô-đun.

Trong lệnh chạy:

```shell
java --add-modules jdk.incubator.vector -cp out VectorModuleDemo
```

các thành phần phối hợp như sau:

| Thành phần | Vai trò trong ví dụ |
| --- | --- |
| `--add-modules jdk.incubator.vector` | Thêm mô-đun Vector API vào tập cần giải quyết |
| `-cp out` | Tìm lớp ứng dụng đã biên dịch trong `out` |
| `VectorModuleDemo` | Chọn lớp chứa điểm khởi chạy |
| `import ...IntVector` | Cho phép dùng tên lớp ngắn trong mã nguồn |

Viết tên đầy đủ `jdk.incubator.vector.IntVector` thay cho import vẫn cần cấu hình mô-đun. Tên lớp đầy đủ không làm thay nhiệm vụ của `--add-modules`.

Cũng không đặt tên lớp sau cờ này:

```text
--add-modules jdk.incubator.vector.IntVector
```

Giá trị đúng là **tên mô-đun** `jdk.incubator.vector`, không phải tên lớp hoặc đường dẫn tệp.

### Đặt cờ trước tên lớp hoặc tệp nguồn

Cách đúng:

```shell
java --add-modules jdk.incubator.vector -cp out VectorModuleDemo
```

Cách dễ gây nhầm:

```shell
java -cp out VectorModuleDemo --add-modules jdk.incubator.vector
```

Ở lệnh thứ hai, phần sau tên lớp là đối số của `main(String[] args)`. Nó không cấu hình mô-đun cho JVM. Trong IDE, tương tự, hãy đặt tùy chọn vào **VM options**, không đặt vào **program arguments**.

## 5. Incubator không phải preview

`jdk.incubator.vector` là incubator module. Riêng ví dụ trong bài chỉ cần `--add-modules`; không cần thêm `--enable-preview` để dùng các thao tác Vector API này.

| Cơ chế | Cách tham gia điển hình | Điều cần nhớ |
| --- | --- | --- |
| Incubator module | Giải quyết mô-đun bằng `--add-modules` hoặc dependency mô-đun phù hợp | API vẫn có thể thay đổi trước khi ổn định |
| Preview feature | Bật `--enable-preview` và cấu hình phiên bản tương ứng | Một cờ riêng, không thay việc giải quyết mô-đun Vector API |

Ví dụ chỉ thêm `--enable-preview` mà không thêm `jdk.incubator.vector` trong trường hợp classpath không giải quyết nguyên nhân thiếu mô-đun.

Nếu cùng chương trình thực sự dùng thêm một preview feature khác, cấu hình hai cơ chế độc lập theo JDK đã chọn. Không mặc định thêm mọi cờ preview cho mọi tính năng chưa chính thức. Sự phân biệt này cũng được nêu trong [hướng dẫn Java 27 của JetBrains](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/).

## 6. Chạy trực tiếp tệp nguồn hoặc đóng gói JAR

### Chạy tệp nguồn

Với cùng `VectorModuleDemo.java` chưa có module descriptor, có thể dùng source-file mode:

```shell
java --add-modules jdk.incubator.vector VectorModuleDemo.java
```

Launcher xét cờ mô-đun cho quá trình biên dịch tệp nguồn và cho việc thực thi. Không cần một lệnh `javac` riêng trong cách chạy này. Cơ chế xử lý tùy chọn source-file mode được mô tả tại [tài liệu java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

Đặt tệp nguồn trong một thư mục thực hành riêng sẽ giúp phân biệt ví dụ này với các dự án có `module-info.java`. Khi đã chọn cách biên dịch ra `out`, tiếp tục dùng lệnh `java -cp out` của phần trước để tránh nhầm hai chế độ chạy.

### Chạy JAR trên classpath

Sau khi biên dịch ví dụ vào `out`, tạo một JAR có main class:

```shell
jar --create --file vector-demo.jar --main-class VectorModuleDemo -C out .
```

Chạy:

```shell
java --add-modules jdk.incubator.vector -jar vector-demo.jar
```

`jar` đóng gói lớp ứng dụng và ghi điểm khởi chạy theo tùy chọn `--main-class`; xem [tài liệu lệnh jar](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html). Trong ví dụ này, JAR không chứa bản sao của Vector API và không tự ghi nhớ cờ `--add-modules` từ lần biên dịch.

Tùy chọn JVM tiếp tục đứng trước `-jar`. Các đối số sau tên JAR được truyền cho chương trình, nên đặt `--add-modules` ở cuối lệnh cũng không kích hoạt mô-đun cho lần chạy đó.

## 7. Nếu dự án có module-info.java

Với ứng dụng JPMS có tên, khai báo dependency tường minh bằng `requires`. Cấu trúc thực hành:

```text
src/
└── learning.vector.demo/
    ├── module-info.java
    └── com/
        └── example/
            └── vector/
                └── VectorModuleDemo.java
```

Nội dung `src/learning.vector.demo/module-info.java`:

```java
module learning.vector.demo {
    requires jdk.incubator.vector;
}
```

Nội dung `src/learning.vector.demo/com/example/vector/VectorModuleDemo.java`:

```java
package com.example.vector;

import jdk.incubator.vector.IntVector;

public class VectorModuleDemo {
    public static void main(String[] args) {
        IntVector values = IntVector.broadcast(IntVector.SPECIES_PREFERRED, 7);
        System.out.println(values.add(5).lane(0));
    }
}
```

Tại thư mục chứa `src`, biên dịch và chạy:

```shell
javac -d mods --module-source-path src -m learning.vector.demo
java --module-path mods -m learning.vector.demo/com.example.vector.VectorModuleDemo
```

Kết quả ứng dụng mong đợi là `12`, ngoài cảnh báo incubator nếu có.

Ở cách tổ chức này, module descriptor yêu cầu `jdk.incubator.vector`, nên module resolution đi theo dependency đó. Không cần lặp lại `--add-modules jdk.incubator.vector` chỉ để đưa dependency đã được khai báo bằng `requires` vào đồ thị mô-đun. Quan hệ phụ thuộc và readability được quy định tại [JLS §7.7.1](https://docs.oracle.com/javase/specs/jls/se27/html/jls-7.html#jls-7.7.1).

Ngược lại, chỉ thêm `--add-modules` không tự cấp quan hệ đọc cho mọi named module trong ứng dụng. Với module dùng Vector API trực tiếp, giữ khai báo `requires jdk.incubator.vector;` để dependency thể hiện ngay trong mã.

Không đưa tên `jdk.incubator.vector` vào `--module-path` như thể đó là một đường dẫn. Trong ví dụ, `--module-path mods` chỉ vị trí module ứng dụng; mô-đun Vector API được tìm trong JDK đang dùng.

## 8. Đồng bộ cấu hình IDE, build và kiểm thử

Cấu hình compiler và cấu hình tiến trình chạy là hai nơi cần kiểm tra riêng:

| Nơi thực thi | Với ứng dụng classpath cần cấu hình gì? |
| --- | --- |
| Compiler của project | Truyền `--add-modules jdk.incubator.vector` tới `javac` |
| Lệnh chạy ứng dụng | Truyền cờ tương ứng vào tùy chọn JVM |
| JVM chạy test hoặc benchmark | Thêm mô-đun cho chính tiến trình đó |
| Tiến trình Java do công cụ build tạo thêm | Kiểm tra đối số JVM mà công cụ truyền thực tế |

Với Maven hoặc Gradle, không xem việc compiler đã có cờ là bằng chứng JVM chạy test cũng có cờ. Cần cấu hình đúng tác vụ/plugin tạo ra từng tiến trình. Với IDE, chọn đúng JDK rồi tách compiler options khỏi VM options.

Nếu dự án là named module có `requires`, ưu tiên giữ dependency đó trong module descriptor. Sau đó kiểm tra ứng dụng hoặc test thực sự chạy theo module path hay đã chuyển về classpath, vì cách chạy thay đổi cơ chế giải quyết mô-đun.

Một ví dụ trong terminal chạy được nhưng IDE báo thiếu `IntVector` thường cần kiểm tra JDK và compiler arguments của IDE trước khi sửa import. Một bài test chạy được trên máy cá nhân nhưng lỗi trong CI cần kiểm tra cả toolchain lẫn câu lệnh khởi chạy trên CI.

## 9. Chẩn đoán theo thông báo và giai đoạn

Thông báo cụ thể thay đổi theo phiên bản, nhưng có thể phân nhóm:

| Biểu hiện | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Compiler báo package không tồn tại hoặc không nhìn thấy | Chưa thêm mô-đun hoặc compiler dùng JDK không có mô-đun | Kiểm tra `javac --version` và cờ compiler |
| `NoClassDefFoundError` liên quan `jdk/incubator/vector/IntVector` | Lần chạy không có mô-đun trong đồ thị phù hợp | Kiểm tra tùy chọn JVM và runtime thực tế |
| `Module jdk.incubator.vector not found` | Runtime không có mô-đun hoặc tên bị viết sai | Kiểm tra `--describe-module` trên đúng runtime |
| Named module báo không đọc được mô-đun Vector API | Thiếu khai báo dependency phù hợp | Thêm `requires` trong module descriptor của thành phần sử dụng |
| Cảnh báo sử dụng incubator module | Mô-đun đang ở trạng thái incubating | Phân biệt warning với lỗi và xem chính sách build |
| IDE chạy được, test runner lỗi | Hai tiến trình có cấu hình khác nhau | So sánh JDK và JVM arguments của từng tiến trình |

Để quan sát module resolution khi chạy ví dụ classpath, dùng:

```shell
java --show-module-resolution --add-modules jdk.incubator.vector -cp out VectorModuleDemo
```

Tìm tên `jdk.incubator.vector` trong phần mô-đun đã giải quyết. Phần ứng dụng vẫn phải chạy ra kết quả mong đợi. Đây là công cụ xem cấu hình, không phải phép đo hiệu năng của các phép toán vector.

Khi kiểm tra tương thích phiên bản, không coi `--release 22` là thao tác nạp Vector API của JDK 22 vào một JDK mới. Với API incubator, hãy chọn toolchain mục tiêu rõ ràng và đối chiếu tài liệu đúng phiên bản thay vì giả định cờ giới hạn phiên bản nguồn cung cấp toàn bộ API incubator lịch sử.

## 10. Cách áp dụng vào bài thực hành tiếp theo

Với một lớp thực hành độc lập, bắt đầu bằng hai lệnh ở đầu bài và giữ compiler/runtime cùng toolchain. Khi chuyển sang JAR, giữ cờ ở bước khởi chạy. Khi chuyển sang named module, đưa dependency vào `module-info.java` bằng `requires` và chạy theo module path.

Sau khi ví dụ nhỏ in đúng tên mô-đun và kết quả, môi trường đã sẵn sàng để học các thao tác như tải dữ liệu, tính toán theo lane và xử lý phần tử cuối mảng. Việc cấu hình mô-đun đúng giúp những bài thực hành đó bắt đầu từ cùng một điều kiện rõ ràng; khả năng tối ưu SIMD cần được đánh giá riêng theo thuật toán và môi trường chạy.