# Unnamed module, automatic module và named module

Khi chuyển một ứng dụng Java 8 lên Java 11 hoặc một phiên bản Java mới hơn, lập trình viên thường gặp những khái niệm như *classpath*, *module path*, *unnamed module*, *automatic module* và *named module*. Đây là các thành phần cốt lõi của **Java Platform Module System (JPMS)**, được đưa vào nền tảng từ Java 9.

Điểm quan trọng nhất là: **không phải cứ dùng JDK mới thì phải viết `module-info.java` ngay**. Mã Java 8 đặt trên classpath vẫn có thể chạy trong mô hình tương thích của JPMS. Nhưng khi ứng dụng, thư viện hoặc công cụ build bắt đầu sử dụng module path, các quy tắc về đọc module, export package và reflection sẽ ảnh hưởng trực tiếp đến việc biên dịch, nạp lớp và thực thi.

Bài học này giải thích ba loại module theo góc nhìn **Java Advance Compatibility Migration**, trong chương **JPMS và nạp lớp**: chúng được tạo ra thế nào, nhìn thấy nhau ra sao, chịu các giới hạn nào, và nên chọn cách chuyển đổi nào khi hệ thống đang có nhiều JAR legacy.

## 1. Những khái niệm nền tảng trước khi so sánh

### 1.1. Classpath và module path

Trước Java 9, hầu hết ứng dụng tìm lớp qua **classpath**: JVM và class loader tra cứu class trong các thư mục/JAR được chỉ định, trong phạm vi quy tắc class loading.

```bash
# Linux/macOS: dấu : ngăn cách các phần tử classpath
java -cp "app.jar:lib/*" com.example.Main

# Windows: dấu ; ngăn cách các phần tử classpath
java -cp "app.jar;lib/*" com.example.Main
```

Từ Java 9 có thêm **module path**, nơi JVM tìm những JAR hoặc thư mục được xem là module:

```bash
java --module-path mods -m com.example.app/com.example.app.Main
```

Hai đường dẫn không có nghĩa giống nhau. **Vị trí đặt JAR** quyết định nó được xử lý theo mô hình classpath hay module path; cùng một JAR có thể mang vai trò khác nhau tùy cách chạy.

### 1.2. Module descriptor và module graph

Một module có tên rõ ràng thường mô tả phụ thuộc và các package được công khai trong `module-info.java`:

```java
module com.example.app {
    requires java.sql;
    exports com.example.app.api;
}
```

Khi khởi chạy hoặc biên dịch chương trình modular, công cụ phân giải các module từ các module gốc (*root modules*) và quan hệ `requires`, tạo thành **module graph**. Một module có tồn tại trên module path không đồng nghĩa nó luôn được giải quyết và tham gia vào graph. Có thể cần `requires`, `--add-modules` hoặc cơ chế phân giải module phù hợp để đưa nó vào.

### 1.3. Ba câu hỏi thường bị gộp làm một

Khi một lớp không thể được sử dụng, nên phân biệt:

1. **Lớp có thể được tìm và nạp không?** Phụ thuộc vào JAR, đường dẫn, class loader và module được phân giải.
2. **Module gọi có được đọc module chứa lớp không?** Phụ thuộc vào quan hệ readability, chẳng hạn `requires`.
3. **Package chứa lớp có được export hoặc open cho kiểu truy cập đang dùng không?** Phụ thuộc `exports`, `opens` và các tùy chọn JVM tương ứng.

Một lỗi có thể xảy ra ở bất kỳ lớp nào. Ví dụ, đặt JAR vào đúng thư mục không tự động cấp quyền truy cập vào mọi package của named module.

## 2. Unnamed module: mã chạy trên classpath

### 2.1. Định nghĩa

**Unnamed module** là module không có tên, chứa các lớp do một class loader nạp từ classpath. Mã không cần khai báo `module-info.java`. Mỗi class loader có unnamed module của riêng nó; vì vậy không nên hiểu rằng toàn bộ JVM chỉ có đúng một unnamed module.

Ví dụ một ứng dụng legacy:

```text
legacy-app/
├── app.jar
└── lib/
    ├── logging.jar
    ├── jdbc-driver.jar
    └── utils.jar
```

Khởi chạy:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Trên Linux/macOS dùng dấu `:`; trên Windows đổi thành `;`. Những lớp do application class loader nạp từ các JAR classpath thông thường sẽ thuộc unnamed module tương ứng, bất kể các JAR có từng được xây dựng như một thư viện riêng.

### 2.2. Đặc điểm quyền truy cập

Unnamed module được thiết kế để hỗ trợ mã legacy:

- Không cần và không có tên module để dùng trong `requires`.
- Có thể đọc các module đã được phân giải trong module graph, nhưng vẫn bị ràng buộc bởi các package mà named module export cho nó.
- Export và open các package của chính nó để hỗ trợ mã trên classpath và reflection theo cơ chế tương thích.
- Không tạo ra ranh giới module rõ ràng giữa các JAR do cùng class loader nạp vào unnamed module.

Mặc dù unnamed module có quyền truy cập rộng theo chiều nó **sử dụng** module khác, điều đó **không có nghĩa** mọi named module có thể tham chiếu ngược lại các lớp trong classpath. Một named module thông thường không thể viết `requires` đến unnamed module.

### 2.3. Vì sao classpath vẫn hữu ích khi migration?

Khi nâng JDK 8 lên 11, tiếp tục chạy trên classpath thường là chiến lược ít thay đổi nhất. Điều này giúp tách hai nhiệm vụ:

- **Nâng runtime:** cập nhật JDK, build tool, dependency và các API đã thay đổi hoặc bị loại bỏ.
- **Module hóa:** thiết kế lại ranh giới package, `requires`, `exports`, `opens` và cơ chế service loading.

Không cần gộp hai nhiệm vụ thành một lần chuyển đổi lớn. Nếu ứng dụng chủ yếu dùng framework legacy hoặc nhiều thư viện chưa có module descriptor ổn định, giữ classpath trong giai đoạn đầu có thể giúp giảm rủi ro.

### 2.4. Giới hạn của unnamed module

Vì các JAR classpath thường không có ranh giới module độc lập, những vấn đề cũ vẫn còn:

- Dependency bị thiếu chỉ được phát hiện khi compile hoặc khi thực thi một đường code.
- Một package có thể được nhiều JAR cùng cung cấp; việc chọn class phụ thuộc cấu hình class loader và classpath.
- Không thể biểu đạt rõ module nào được phép dùng API nội bộ của JAR khác bằng `exports`.
- Một số dependency được nạp gián tiếp qua reflection và cấu hình nên khó kiểm kê đầy đủ.

Unnamed module là cơ chế tương thích, không phải giải pháp thay thế hoàn toàn cho thiết kế module rõ ràng.

## 3. Automatic module: cầu nối từ JAR cũ sang module path

### 3.1. Automatic module xuất hiện khi nào?

Một JAR **không có module descriptor** nhưng được đặt trên **module path** có thể được xử lý như **automatic module**. JVM gán cho nó một tên module và những đặc quyền tương thích nhất định để nó có thể tham gia module graph.

Ví dụ:

```text
mods/
├── com.example.app/
└── legacy-utils-1.2.jar   # JAR chưa có module-info.class
```

Nếu `legacy-utils-1.2.jar` được đặt trên module path và được phân giải vào graph, nó sẽ hoạt động như automatic module thay vì một JAR classpath thông thường.

Không phải cứ di chuyển file sang thư mục tên `mods` thì nó tự nhiên thành module; yếu tố quyết định là **cách công cụ Java được gọi với `--module-path`**.

### 3.2. Tên của automatic module

Tên automatic module được xác định theo thứ tự thông thường:

1. Nếu manifest của JAR có thuộc tính `Automatic-Module-Name`, dùng tên đó.
2. Nếu không, công cụ suy ra tên từ tên file JAR theo quy tắc chuẩn hóa và loại bỏ phần version phù hợp.

Ví dụ manifest của một thư viện:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.vendor.legacyutils
```

Một named module có thể khai báo phụ thuộc:

```java
module com.example.app {
    requires com.vendor.legacyutils;
}
```

Sử dụng tên module do nhà cung cấp công bố thường ổn định hơn việc dựa vào tên suy ra từ file. Khi thư viện đổi tên file, cách đặt version hoặc chuyển sang module descriptor thật, tên suy ra có thể đổi và khiến `requires` không còn phân giải được.

Có thể tra tên thực tế bằng:

```bash
jar --describe-module --file path/to/legacy-utils-1.2.jar
```

Với JAR chưa modular hóa, công cụ có thể thông báo rằng không tìm thấy descriptor và hiển thị tên automatic module suy ra. Kết quả này đáng tin hơn việc tự đoán tên từ filename.

### 3.3. Đặc tính truy cập của automatic module

Automatic module được thiết kế cho khả năng tương thích với JAR cũ. Về nguyên tắc, nó:

- Có **tên module** để các named module khác có thể `requires`.
- Đọc các module được phân giải khác và có khả năng sử dụng mã trong unnamed module theo cơ chế tương thích của automatic module.
- Export tất cả package của mình để module khác có thể sử dụng các kiểu public.
- Open các package của mình cho reflection, hỗ trợ framework legacy cần truy cập sâu.

Những đặc quyền này giúp giảm công sức đưa thư viện cũ vào một graph modular. Tuy nhiên, automatic module **chưa có contract đóng gói tường minh**: mọi package bị phơi ra, kể cả package vốn chỉ là implementation detail. Vì thế không nên coi nó là thiết kế module cuối cùng.

### 3.4. Automatic module không giải quyết mọi dependency

Một automatic module vẫn có thể gặp vấn đề:

- Hai JAR trên module path chứa cùng một package (*split package*).
- Một JAR dùng tên module suy ra không ổn định.
- Thư viện tham chiếu reflection hoặc API nội bộ của JDK bị đóng gói chặt.
- Dependency runtime không được phân giải hoặc không có trên đường dẫn cần thiết.
- Framework tự tạo class, quét classpath hoặc dùng custom class loader với giả định khác mô hình JPMS.

Nếu automatic module cần sử dụng một JAR khác trên classpath, đó không có nghĩa ứng dụng named module bao quanh nó cũng được phép tham chiếu trực tiếp vào JAR classpath. Phải xét từng module và luồng phụ thuộc cụ thể.

### 3.5. Vai trò chuyển tiếp trong lộ trình migration

Automatic module phù hợp khi thư viện chưa có `module-info.java` nhưng ứng dụng mới cần dùng `requires` đến nó. Khi nhà cung cấp phát hành module descriptor chính thức, nên kiểm tra khả năng tương thích tên module và ranh giới package trước khi thay thế JAR.

Đừng tự chuyển mọi dependency sang module path chỉ để “đạt chuẩn JPMS”. Trong nhiều dự án, một số JAR legacy giữ trên classpath là lựa chọn thực tế hơn cho đến khi hệ sinh thái hỗ trợ đầy đủ.

## 4. Named module: module có danh tính và contract rõ ràng

### 4.1. Named module là gì?

**Named module** có tên được JPMS nhận diện. Trong ngữ cảnh ứng dụng, named module thường là **explicit named module**: module khai báo một descriptor qua `module-info.java` và được biên dịch thành `module-info.class`.

Ví dụ:

```java
module com.example.orders {
    requires java.sql;
    requires java.logging;

    exports com.example.orders.api;
}
```

Module `com.example.orders` nói rõ rằng nó đọc `java.sql`, `java.logging` và công khai package API của riêng mình. Package khác không được export vẫn có thể dùng bên trong module nhưng không trở thành API thông thường cho module bên ngoài.

Chú ý về thuật ngữ: **automatic module cũng là một module có tên**. Khi so sánh ba nhóm trong bài, “named module” thường được dùng để chỉ **explicit named module**, đối lập với automatic module vốn được gán tên tự động. Trong phân loại kỹ thuật đầy đủ, hai nhóm đều có tên.

### 4.2. Những chỉ thị thường gặp trong `module-info.java`

| Chỉ thị | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `requires m` | Đọc module `m` để dùng API được export. | Ứng dụng cần `java.sql`. |
| `requires transitive m` | Cho phép module đọc module hiện tại cũng đọc được `m` theo quan hệ transitive. | Public API của module hiện tại trả về kiểu thuộc `m`. |
| `requires static m` | Cần module ở thời điểm biên dịch nhưng không yêu cầu bắt buộc ở runtime. | Phụ thuộc chỉ cần cho compile/annotation. |
| `exports p` | Export package `p` cho các module khác. | Công khai package API. |
| `exports p to m` | Export package chỉ cho một số module chỉ định. | API nội bộ chia sẻ có kiểm soát. |
| `opens p` | Cho phép deep reflection đối với package `p`. | ORM/serializer truy cập field không public. |
| `opens p to m` | Chỉ open package cho module chỉ định. | Mở entity cho một ORM framework. |
| `uses s` | Module sử dụng service `s`. | `ServiceLoader` tìm provider. |
| `provides s with impl` | Module cung cấp implementation của service `s`. | Module triển khai một SPI. |

Ngoài ra, `open module` cho phép deep reflection vào toàn bộ package của module; điều này khác với việc export mọi package cho truy cập Java thông thường. Nên mở từng package cụ thể khi có thể.

### 4.3. Ví dụ hai named module độc lập

Giả sử có cấu trúc mã nguồn:

```text
src/
├── com.example.greeting/
│   ├── module-info.java
│   └── com/example/greeting/api/Greetings.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Module cung cấp API:

```java
// src/com.example.greeting/module-info.java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

```java
// src/com.example.greeting/com/example/greeting/api/Greetings.java
package com.example.greeting.api;

public final class Greetings {
    private Greetings() {}

    public static String hello(String name) {
        return "Xin chào, " + name;
    }
}
```

Module ứng dụng:

```java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.greeting;
}
```

```java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.greeting.api.Greetings;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greetings.hello("Java"));
    }
}
```

Ví dụ biên dịch theo từng module từ thư mục gốc dự án:

```bash
# Bước 1: biên dịch module cung cấp API
javac -d mods/com.example.greeting \
  src/com.example.greeting/module-info.java \
  src/com.example.greeting/com/example/greeting/api/Greetings.java

# Bước 2: biên dịch module ứng dụng với module path
javac --module-path mods -d mods/com.example.app \
  src/com.example.app/module-info.java \
  src/com.example.app/com/example/app/Main.java

# Bước 3: chạy main class của named module
java --module-path mods -m com.example.app/com.example.app.Main
```

Các lệnh minh họa cho shell Unix, nơi `\` nối dòng. Trên Windows PowerShell hoặc `cmd`, viết mỗi lệnh trên một dòng hoặc dùng cú pháp nối dòng phù hợp. Với Maven/Gradle, để plugin build tổ chức module path và compile task thay vì tự hardcode toàn bộ câu lệnh.

### 4.4. Không thể `requires` một unnamed module

Ví dụ mã cũ đặt trong `legacy.jar` trên classpath cung cấp `com.legacy.Helper`. Một explicit named module không thể viết:

```java
module com.example.app {
    // Không hợp lệ: unnamed module không có tên để requires.
    requires unnamed;
}
```

Để xử lý, có thể chọn:

1. Chuyển `legacy.jar` lên module path để dùng như automatic module (nếu không có xung đột package).
2. Nâng lên phiên bản thư viện đã có explicit module descriptor.
3. Giữ phần ứng dụng còn phụ thuộc vào JAR đó trên classpath trong giai đoạn chuyển tiếp.
4. Chỉ trong tình huống đặc biệt, dùng tùy chọn `--add-reads` để thêm quan hệ đọc đến `ALL-UNNAMED`, đồng thời cấu hình nhất quán lúc compile và runtime.

Đường chuyển đổi nên ưu tiên dependency có tên module ổn định; `--add-reads` thường là workaround có giới hạn, không thay thế được thiết kế phụ thuộc rõ ràng.

## 5. Bảng so sánh ba mô hình

| Tiêu chí | Unnamed module | Automatic module | Explicit named module |
| --- | --- | --- | --- |
| Nguồn lớp phổ biến | Classpath | JAR chưa có descriptor trên module path | JAR/thư mục có `module-info.class` trên module path |
| Có tên module? | Không | Có, từ manifest hoặc suy ra | Có, khai báo rõ trong descriptor |
| Cần `module-info.java`? | Không | Không | Có trong source tương ứng, hoặc descriptor được tạo khi xây module |
| Quan hệ đọc | Cơ chế tương thích rộng với các module đã phân giải | Đọc rộng để tương thích thư viện legacy | Theo `requires` và quy tắc JPMS |
| Package export | Package của chính nó được export rộng | Tất cả package được export | Chỉ package `exports` hoặc cấu hình bổ sung |
| Deep reflection | Package của chính nó được mở rộng | Các package được mở để tương thích | Theo `opens`, `open module` hoặc cấu hình bổ sung |
| Mức đóng gói API | Thấp | Thấp, vì tự export nhiều package | Có thể cao, nhờ khai báo ranh giới |
| Trường hợp dùng | Ứng dụng/JAR legacy, migration ban đầu | Cầu nối để named module phụ thuộc JAR cũ | Module có kiến trúc và contract rõ ràng |

Điểm cần nhớ: **automatic module có tên nhưng không có descriptor tường minh**, còn **unnamed module không có tên dù code trong đó vẫn được JPMS quản lý**.

## 6. Readability, exports, opens và khả năng nạp lớp

### 6.1. “Đọc được module” khác “truy cập được package”

Với explicit named module `com.example.app`:

```java
module com.example.app {
    requires com.example.library;
}
```

Nếu `com.example.library` không export package `com.example.library.internal`, source của `com.example.app` không thể sử dụng kiểu trong package đó theo cách truy cập Java thông thường, dù nó đã khai báo `requires com.example.library`.

Cần đồng thời đáp ứng:

```text
Module gọi đọc được module đích
                 +
Package đích được export tới module gọi
                 +
Quy tắc public/protected/package/private của Java cho phép
                 =
Truy cập kiểu/thành viên bằng mã Java thông thường
```

### 6.2. `exports` không tự cho phép deep reflection

Framework như ORM hoặc serializer đôi khi cần truy cập constructor/field không public bằng reflection. Export package không đồng nghĩa cho phép deep reflection tùy ý.

Ví dụ:

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.entity to org.hibernate.orm.core;
}
```

Trong ví dụ này, package entity được mở cho module ORM có tên tương ứng; package API được export cho truy cập Java thông thường. Tên module của ORM phải được xác định từ phiên bản thư viện thực tế. Nếu framework nằm trên classpath hoặc module graph được tổ chức khác, cấu hình cũng cần điều chỉnh.

Khi hệ thống đang dùng thư viện tự sinh proxy, reflection hoặc serialization, phải xem **cả module graph lẫn class loader thực tế**. Một class được nạp thành công vẫn có thể gây `InaccessibleObjectException` khi framework cố truy cập sâu vào thành viên không được mở.

### 6.3. Named module và unnamed module không có quan hệ đối xứng

Thực tế thường gây nhầm lẫn:

- Mã ở unnamed module có thể gọi các API được export bởi named module đã phân giải.
- Explicit named module không tự nhiên đọc code nằm trong unnamed module; không thể thêm `requires` bằng tên vì unnamed module không có tên.
- Automatic module được thiết kế để làm cầu nối và có quy tắc đọc rộng hơn explicit named module.

Do đó, hướng phụ thuộc rất quan trọng. **Một ứng dụng classpath gọi thư viện modular** và **một ứng dụng modular gọi thư viện classpath** không phải hai trường hợp đối xứng.

## 7. JPMS không thay thế ClassLoader

### 7.1. Module và class loader giải quyết các vấn đề khác nhau

Class loader chịu trách nhiệm định vị, định nghĩa và nạp class theo mô hình class loading. Module system mô tả quan hệ đọc giữa module và khả năng nhìn thấy package. Một class được gắn với module trong quá trình định nghĩa, nhưng vẫn phải có class loader chịu trách nhiệm nạp nó.

Trong ứng dụng thực tế có thể có:

- Bootstrap/platform/application class loader của JVM.
- Class loader do application server, servlet container hoặc framework tạo ra.
- `URLClassLoader` và custom class loader cho plugin hoặc JAR bên ngoài.
- Thread context class loader dùng để chọn phạm vi tìm provider/resource.

Mỗi class loader có unnamed module của riêng mình. Những lớp được nạp bởi class loader khác nhau có thể mang cùng tên package và class nhưng không đồng nghĩa là cùng một runtime type.

### 7.2. Xác định module của class khi chạy

Java 9+ có API `Class.getModule()`:

```java
public final class ModuleInspector {
    public static void main(String[] args) {
        inspect(String.class);
        inspect(ModuleInspector.class);
    }

    private static void inspect(Class<?> type) {
        Module module = type.getModule();
        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());
        System.out.println("Named: " + module.isNamed());
        System.out.println("Loader: " + type.getClassLoader());
    }
}
```

`String` thuộc named module `java.base`. Nếu `ModuleInspector` chạy trên classpath, `getModule().isNamed()` của lớp này là `false` và `getName()` trả về `null`. Nếu nó được đưa vào một explicit named module, kết quả sẽ tương ứng với module đó.

`ClassLoader` của các lớp nền tảng có thể hiển thị `null` nếu class được nạp bởi bootstrap loader. Không nên coi `null` là lỗi.

### 7.3. Module layer và plugin architecture

JPMS còn có khái niệm **module layer**, cho phép tạo các tập module có cấu hình phân giải và class loader riêng. Một kiến trúc plugin có thể dùng layer mới để nạp module được bổ sung sau khi ứng dụng khởi động.

Tuy nhiên, việc dùng layer không làm mất các quy tắc readability, package exports hoặc service loading. Cần thiết kế module graph, class loader và vòng đời plugin thống nhất; không thể chỉ đặt JAR vào một thư mục rồi kỳ vọng mọi lớp trở nên nhìn thấy từ mọi module.

Với ứng dụng có custom class loader từ trước Java 9, migration nên khảo sát cả cơ chế chọn class loader và cách các plugin được đóng gói. Đừng thay toàn bộ kiến trúc plugin sang layer trong cùng đợt nâng JDK nếu chưa có nhu cầu rõ ràng.

## 8. Ví dụ chuyển tiếp: named module phụ thuộc JAR legacy

Giả sử ứng dụng `com.example.app` muốn sử dụng thư viện `vendor-utils.jar` vốn được phát hành cho Java 8 và chưa có `module-info.class`.

### Cách A: toàn bộ ứng dụng vẫn dùng classpath

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Đây là lựa chọn phù hợp khi đang ưu tiên nâng runtime trước, và thư viện/framework chưa sẵn sàng module hóa. Không cần `module-info.java` cho ứng dụng.

### Cách B: đưa JAR legacy lên module path như automatic module

Thư viện có thể công bố trong manifest:

```text
Automatic-Module-Name: com.vendor.utils
```

Khi đó ứng dụng explicit named module có thể khai báo:

```java
module com.example.app {
    requires com.vendor.utils;
}
```

Khởi chạy theo module path:

```bash
java --module-path "mods:lib/vendor-utils.jar" \
  -m com.example.app/com.example.app.Main
```

Lệnh dùng dấu `:` để phân tách đường dẫn trên Linux/macOS; trên Windows dùng `;`. Cần bảo đảm tên module đúng với metadata của JAR, và package của thư viện không gây split package với các module khác.

### Cách C: dùng phiên bản thư viện đã có descriptor

Khi nhà cung cấp phát hành thư viện có `module-info.class`, dùng đúng tên module do nhà cung cấp công bố và kiểm tra lại API được export, package được open, tên service provider và compatibility với version đang chạy.

Cách C thường giúp có ranh giới module rõ ràng hơn, nhưng không nên mặc định thư viện mới giữ mọi API nội bộ từng được automatic module export rộng rãi. Nếu ứng dụng đang dùng các package nội bộ, việc đổi từ automatic module sang explicit module có thể tạo lỗi compile hoặc runtime.

## 9. Split package, duplicate module và các lỗi phân giải

### 9.1. Split package là gì?

**Split package** là trường hợp một package được phân phối qua nhiều module. Ví dụ:

```text
legacy-a.jar  -> com.vendor.shared.A
legacy-b.jar  -> com.vendor.shared.B
```

Trên classpath, hai JAR này có thể được nạp bởi cùng một class loader. Nhưng khi đưa thành hai module trên module path, JPMS áp dụng những ràng buộc đóng gói chặt hơn; module graph có thể không được phân giải hoặc gây lỗi nếu cùng một package xuất hiện ở các module không thể cùng tồn tại trong cấu hình đã chọn.

Cách xử lý có thể gồm:

- Nâng lên bản thư viện có cấu trúc package phù hợp JPMS.
- Gộp các JAR nếu được nhà cung cấp hỗ trợ.
- Loại bỏ dependency trùng hoặc thay thế implementation.
- Giữ các thành phần chưa thể tách package trên classpath khi migration từng bước.

Đừng dùng shading hoặc đổi package hàng loạt nếu chưa đánh giá reflection, serialization, resource name và compatibility với client khác.

### 9.2. Tên module trùng hoặc không ổn định

Nếu hai JAR khác nhau có cùng module name trên module path, việc lựa chọn/phân giải có thể không như mong muốn hoặc gây lỗi. Với automatic module, tên suy ra từ filename càng làm vấn đề khó theo dõi.

Thực hành phù hợp là ghi lại:

- Đường dẫn JAR thực tế.
- Tên module được công cụ xác định.
- Phiên bản dependency.
- JAR nào được đưa vào module graph.

Thay vì đoán, dùng `jar --describe-module` và các chế độ hiển thị phân giải module.

### 9.3. Lỗi khi module không được phân giải

Một JAR nằm trên module path nhưng không được phân giải vào graph thì chưa chắc có thể sử dụng. Với ứng dụng khởi động trên classpath nhưng cần một named module ngoài JDK, đôi khi phải chỉ định `--add-modules`:

```bash
java --module-path mods \
  --add-modules com.example.greeting \
  -cp app.jar \
  com.example.Main
```

Điều kiện: `com.example.greeting` phải tồn tại và export package mà code classpath sử dụng. `--add-modules` giúp đưa module vào tập phân giải; nó không mở package nội bộ hay bỏ qua `exports`.

## 10. Reflection, `exports`, `opens` và các cờ chuyển tiếp

### 10.1. Hai loại truy cập cần xử lý riêng

Khi di chuyển thư viện hoặc ứng dụng từ unnamed/automatic sang explicit named module, một framework có thể báo lỗi vì package trước đó được mở rộng rãi không còn open nữa.

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý ưu tiên |
| --- | --- | --- |
| Compiler nói package không visible | Module chưa đọc module chứa API, hoặc package không export | Sửa `requires`, `exports` và dependency graph. |
| `IllegalAccessError` | Bytecode truy cập vào package/type bị ràng buộc module | Nâng thư viện hoặc sửa module descriptor để export đúng phạm vi. |
| `InaccessibleObjectException` | Framework muốn deep reflection vào package chưa open | Nâng framework; dùng `opens` cho package cần thiết. |
| `ClassNotFoundException` | Class loader không tìm được lớp hoặc JAR không được nạp đúng đường | Kiểm tra classpath, module path, cấu hình plugin và nguồn class. |
| `NoClassDefFoundError` | Class thiếu ở runtime hoặc lỗi khởi tạo trước đó | Kiểm tra dependency/runtime configuration và nguyên nhân sâu hơn trong log. |

### 10.2. `--add-exports` và `--add-opens`

Hai tùy chọn có thể dùng như giải pháp chuyển tiếp khi chưa chỉnh được descriptor của thư viện:

```bash
# Ví dụ mở một package cho code trên classpath để reflection sâu
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar

# Ví dụ export package nội bộ cho code trên classpath
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
```

`ALL-UNNAMED` là mục tiêu chỉ các unnamed module, thường dùng khi framework đặt trên classpath. Cần xác định chính xác module đích nếu framework đã là named module. Chỉ dùng những cờ thật sự cần và có kế hoạch bỏ; không mở nhiều package chỉ để che lỗi.

### 10.3. `--add-reads` trong tình huống đặc biệt

Nếu một explicit named module chưa thể bỏ phụ thuộc vào mã classpath, có thể gặp ví dụ chuyển tiếp:

```bash
--add-reads com.example.app=ALL-UNNAMED
```

Tùy chọn này thêm quan hệ readability từ module được nêu đến unnamed modules. Nó không tự đóng gói, phân phối hoặc sửa class loader cho các JAR classpath. Với source code được compile modular, thường cũng phải bố trí cấu hình compiler tương ứng; thêm cờ chỉ ở runtime không làm source compile vượt qua mọi giới hạn của JPMS.

Không nên lấy cờ này làm thiết kế lâu dài nếu có thể chuyển dependency thành module có tên ổn định.

## 11. `ServiceLoader` và module boundaries

Ứng dụng Java cũ thường phát hiện implementation qua file `META-INF/services/<service-interface>` trong JAR classpath. Named module có cách công bố service rõ ràng hơn bằng `uses` và `provides`.

Ví dụ module định nghĩa service:

```java
module com.example.spi {
    exports com.example.spi;
}
```

Module consumer:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.MessageProvider;
}
```

Module provider:

```java
module com.example.provider {
    requires com.example.spi;
    provides com.example.spi.MessageProvider
        with com.example.provider.SimpleMessageProvider;
}
```

Ở runtime, consumer có thể dùng:

```java
ServiceLoader<MessageProvider> providers =
    ServiceLoader.load(MessageProvider.class);

for (MessageProvider provider : providers) {
    System.out.println(provider.message());
}
```

Với thư viện legacy là automatic module hoặc nằm trên classpath, cần kiểm tra metadata provider tương ứng. Nếu provider không được phân giải/nạp trong cấu hình modular, việc class tồn tại trong JAR vẫn chưa đủ để `ServiceLoader` tìm thấy.

Trong migration, nên kiểm tra resource `META-INF/services`, module descriptor, class loader ngữ cảnh và các provider thực sự được dùng ở runtime.

## 12. Công cụ quan sát và chẩn đoán JPMS

### 12.1. Xem danh sách module của runtime

```bash
java --list-modules
```

Lệnh hiển thị module mà runtime/cấu hình hiện tại nhìn thấy theo cách lệnh được gọi. Không coi danh sách này là bằng chứng rằng mọi JAR dependency của ứng dụng đã được phân giải vào graph khi khởi chạy theo cấu hình riêng.

### 12.2. Xem descriptor một module

```bash
java --describe-module java.sql
```

Lệnh giúp xem dependency, package export và thông tin descriptor của module có tên.

### 12.3. Xem module name của một JAR

```bash
jar --describe-module --file path/to/library.jar
```

Hữu ích khi cần phân biệt explicit module và automatic module, đặc biệt trước khi viết `requires`.

### 12.4. Quan sát phân giải module khi chạy

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.example.app/com.example.app.Main
```

Thay đường dẫn và module name theo dự án. Log giúp thấy module gốc và các quan hệ được phân giải. Không dùng kết quả của một lần chạy để kết luận cho mọi profile nếu mỗi profile có module path khác nhau.

### 12.5. Phân tích dependency bằng `jdeps`

```bash
# Phân tích dependency ở mức class/package
jdeps --recursive path/to/application.jar

# Xem dependency module mà công cụ xác định được
jdeps --print-module-deps path/to/application.jar
```

`jdeps` hữu ích để tìm phụ thuộc tĩnh và gợi ý các module nền tảng cần thiết. Công cụ không tự biết mọi class được nạp bằng reflection, tên lấy từ cấu hình, plugin tải lúc chạy hoặc native integration. Vì vậy, khi lập runtime image tùy chỉnh bằng `jlink`, cần bổ sung kiểm thử thực tế và kiểm tra các provider cần thiết.

## 13. Quy trình migration từ classpath sang mô hình modular

### Giai đoạn 1: Giữ classpath để xác nhận JDK mới

Chạy ứng dụng legacy trên JDK mục tiêu mà chưa module hóa toàn bộ. Cập nhật build tool, dependency, API bị tách và cấu hình runtime; ghi lại baseline về build, test và startup.

### Giai đoạn 2: Kiểm kê JAR và class loader

Lập danh sách dependency trực tiếp/bắc cầu, JAR được application server cung cấp, plugin directory, reflection, service provider và cơ chế tạo/nạp class động. Ghi riêng các thành phần nằm ngoài dependency graph.

### Giai đoạn 3: Phân loại từng thư viện

Chia dependency thành ba nhóm:

- Đã có explicit module descriptor.
- Chưa có descriptor nhưng có tên automatic module ổn định hoặc có thể sử dụng trên module path.
- Chưa sẵn sàng module path do split package, reflection, class loader đặc biệt hoặc dependency không rõ.

Không giả định một thư viện hỗ trợ Java 11 đồng nghĩa nó đã hỗ trợ module path tốt.

### Giai đoạn 4: Thử module hóa vùng lõi có ranh giới rõ

Bắt đầu từ module có API công khai nhỏ, phụ thuộc ít và không phải framework khởi động toàn hệ thống. Viết `module-info.java` với `requires` và `exports` tối thiểu, rồi kiểm tra compile/run theo module path.

### Giai đoạn 5: Xử lý reflection và service loading

Với framework cần deep reflection, dùng `opens` theo package/module cụ thể. Với provider, dùng `uses`/`provides` hoặc metadata service tương thích. Kiểm tra module graph và nguồn class được nạp thật.

### Giai đoạn 6: Giải quyết split package và phụ thuộc legacy

Nâng thư viện, loại bỏ JAR trùng, điều chỉnh cấu trúc package hoặc tạm thời duy trì một phần trên classpath. Tránh gộp những thay đổi phá tương thích API vào cùng một đợt nếu không cần.

### Giai đoạn 7: Chuẩn hóa build và release

Đảm bảo cấu hình Maven/Gradle, CI, packaging và runtime thống nhất về module path/classpath. Ghi tên module chính thức, phiên bản JDK, module graph và những workaround như `--add-opens`/`--add-reads` còn lại.

### Giai đoạn 8: Kiểm thử và phương án rollback

Chạy integration test, startup/shutdown, reflection, serialization, database driver, logging, security agent và plugin loading. Giữ kế hoạch rollback nếu lỗi chỉ xuất hiện trong một profile production. Module hóa là thay đổi kiến trúc, cần test nhiều hơn việc chỉ chạy `javac` thành công.

## 14. Những hiểu lầm thường gặp

**“Đặt JAR lên module path thì nó luôn được dùng.”** Không hẳn. Module phải được phân giải vào graph; một entry trên đường dẫn không bảo đảm mọi class đã được nạp.

**“Automatic module là unnamed module được đổi tên.”** Không chính xác. Automatic module có tên và có thể được `requires`; unnamed module không có tên. Automatic module được áp dụng cơ chế đọc/export/open tương thích, nhưng vị trí và quan hệ với module graph khác classpath.

**“Một named module chỉ cần `requires` là truy cập được mọi class.”** Sai. Package đích còn phải được export, thành viên phải đáp ứng Java access control và class phải có thể được nạp theo cấu hình.

**“`exports` là đủ cho ORM reflection.”** Không phải lúc nào cũng đúng. Deep reflection thường cần `opens`, và phải tính đúng named module hoặc unnamed module gọi reflection.

**“Ứng dụng Java 11 bắt buộc có `module-info.java`.”** Sai. Classpath và unnamed module vẫn là mô hình hợp lệ.

**“JAR có `Automatic-Module-Name` đã là explicit module.”** Sai. Thuộc tính manifest chỉ cung cấp tên ổn định khi JAR được dùng như automatic module; nó không tương đương một module descriptor với `requires`, `exports`, `opens` riêng.

**“Nếu `jdeps` không báo lỗi thì JPMS đã tương thích.”** Không đủ. Phân tích tĩnh có thể bỏ sót reflection, service loading, native library, cấu hình và plugin được nạp động.

**“Module system thay thế class loader.”** Sai. Class loader vẫn chịu trách nhiệm nạp class; module graph thêm các ràng buộc về readability và package visibility.

## 15. Checklist dành cho dự án Java Advance Compatibility Migration

- [ ] Đã xác định phần ứng dụng nào chạy trên classpath và phần nào dùng module path.
- [ ] Đã phân biệt unnamed, automatic và explicit named module trong runtime hiện tại.
- [ ] Đã lấy đúng tên automatic module bằng `jar --describe-module`, không đoán từ filename.
- [ ] Đã kiểm tra các module cần thiết thực sự được phân giải, không chỉ tồn tại trên module path.
- [ ] Đã đánh giá `requires`, readability và package `exports` của các explicit modules.
- [ ] Đã kiểm tra reflection và các package phải `opens` cho framework.
- [ ] Đã tìm split package, module name trùng và JAR không tương thích module path.
- [ ] Đã rà soát class loader của application server, plugin và các dependency nạp ngoài build.
- [ ] Đã kiểm tra `META-INF/services`, `uses`/`provides` và provider ở runtime.
- [ ] Đã xác định mọi `--add-modules`, `--add-reads`, `--add-exports`, `--add-opens` còn dùng và kế hoạch loại bỏ workaround.
- [ ] Đã thử build/run trên JDK mục tiêu và kiểm thử các luồng nghiệp vụ có reflection, driver, serialization hoặc plugin.
- [ ] Đã cập nhật tài liệu build/deploy, dependency, module graph và rollback plan.

## 16. Kết luận

Ba mô hình **unnamed module**, **automatic module** và **explicit named module** cho phép Java kết hợp khả năng tương thích với ứng dụng cũ và kiến trúc module có ranh giới rõ ràng. Unnamed module hỗ trợ classpath truyền thống; automatic module đóng vai trò cầu nối để JAR chưa modular hóa tham gia module graph; explicit named module công bố tường minh quan hệ phụ thuộc, package export và quyền reflection.

Đối với Java compatibility migration, cách tiếp cận an toàn là **nâng runtime trước nếu cần, module hóa có chọn lọc sau**, kiểm tra từng dependency và phân biệt ba lớp vấn đề: class có được nạp không, module có đọc được nhau không, và package có cho phép kiểu truy cập đang dùng không. Khi các câu hỏi này được trả lời bằng cấu hình và kiểm thử thực tế, việc chuyển đổi sang JPMS sẽ dễ kiểm soát hơn thay vì trở thành một đợt thay đổi toàn diện khó chẩn đoán.
