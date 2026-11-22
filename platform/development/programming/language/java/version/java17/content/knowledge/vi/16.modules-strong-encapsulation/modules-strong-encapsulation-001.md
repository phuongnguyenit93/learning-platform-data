# Named module, unnamed module và automatic module trong Java 17

> **Chủ đề:** Java 17
> **Chương:** Module và đóng gói mạnh

## 1. Tổng quan

Java Platform Module System (JPMS) nhóm các package thành module. Một module có thể khai báo dependency, xác định package được công khai và giới hạn truy cập reflection. Trong Java 17 có ba trường hợp cần phân biệt:

1. **Named module:** module có tên và descriptor được khai báo bằng `module-info.java` hoặc `module-info.class`.
2. **Unnamed module:** module không tên, thường chứa các lớp được nạp từ classpath.
3. **Automatic module:** JAR chưa có module descriptor nhưng được đặt trên module path; Java tạo một named module từ JAR đó.

Automatic module vẫn là một **named module**. Điểm khác biệt là descriptor của nó được suy ra thay vì do tác giả khai báo tường minh.

## 2. Named module: module được khai báo tường minh

Một named module có tên hợp lệ và descriptor. Với mã nguồn, descriptor nằm trong file `module-info.java` ở gốc source module. Khi biên dịch, file này trở thành `module-info.class`.

### 2.1. Ví dụ module descriptor

Giả sử ứng dụng quản lý đơn hàng cần sử dụng logging và công khai API cho module khác:

```java
module com.acme.orders {
    requires java.logging;

    exports com.acme.orders.api;

    opens com.acme.orders.persistence
        to com.fasterxml.jackson.databind;
}
```

Descriptor trên thể hiện ba quan hệ:

- `requires java.logging`: module hiện tại cần đọc module `java.logging`.
- `exports com.acme.orders.api`: cho phép code thuộc module khác truy cập các kiểu `public`/`protected` trong package API được export và các thành viên tương ứng.
- `opens com.acme.orders.persistence to ...`: cho phép framework được chỉ định dùng reflection sâu trên package persistence ở runtime, kể cả với thành viên không công khai.

Tên module thường dùng quy ước đảo ngược tên miền, ví dụ `com.acme.orders`. Tên module gồm một hoặc nhiều Java identifier ngăn cách bằng dấu chấm. Tên package và tên module là hai định danh khác nhau, dù thường được đặt theo cùng quy ước.

### 2.2. Module kiểm soát cả phụ thuộc và package được công khai

Một named module có hai hướng kiểm soát:

| Hướng | Cơ chế | Câu hỏi được trả lời |
|---|---|---|
| Module hiện tại sử dụng module khác | `requires` | Code của tôi được phép đọc những module nào? |
| Module khác sử dụng module hiện tại | `exports` / `opens` | Tôi công khai package nào và cho phép reflection ở đâu? |

Ví dụ, nếu module `com.acme.orders` có class `public` trong package `com.acme.orders.internal` nhưng không export package này, code của module khác vẫn không thể tham chiếu class đó như một API thông thường. Từ khóa `public` không tự vượt qua ranh giới module.

Điều này giúp module giữ chi tiết triển khai bên trong và công bố một bề mặt API nhỏ, rõ ràng.

### 2.3. Phân biệt requires, exports và opens

```java
module com.acme.application {
    requires com.acme.orders;
}

module com.acme.orders {
    exports com.acme.orders.api;
}
```

`requires` tạo quan hệ **readability**: module application được phép đọc module orders. Nhưng việc đọc module không tự động làm mọi package của orders có thể truy cập. Package cần được module orders export.

`exports` cấp quyền truy cập thông thường ở compile time và runtime cho các kiểu và thành viên `public`/`protected` thuộc package được export.

`opens` chủ yếu phục vụ reflection ở runtime. Nó không làm package trở thành API để code module khác import và tham chiếu kiểu ở compile time.

| Chỉ thị | Truy cập code thông thường | Reflection |
|---|---|---|
| `exports p;` | Có, với kiểu/thành viên `public` và `protected` | Có với phạm vi `public`/`protected` tương ứng |
| `opens p;` | Không cấp quyền tham chiếu compile-time qua package đó | Cho phép reflection sâu vào các kiểu và thành viên trong package |
| Không export, không open | Không | Không, đối với code bên ngoài module |

Nếu một module dùng framework serialization, ORM hoặc dependency injection cần reflection sâu, hãy mở đúng package cho framework tương ứng thay vì mở toàn bộ module một cách tùy tiện.

### 2.4. Open module

Java cũng cho phép khai báo:

```java
open module com.acme.application {
    requires com.acme.orders;
    exports com.acme.application.api;
}
```

Một `open module` mở tất cả package của nó cho reflection ở runtime. Nó vẫn chỉ export package được khai báo tường minh để truy cập thông thường.

Trong một `open module`, không được viết thêm chỉ thị `opens` trong descriptor. Nếu chỉ một vài package cần reflection, dùng module bình thường và các chỉ thị `opens` có phạm vi hẹp.

## 3. Unnamed module: các lớp không thuộc named module

Unnamed module được Java cung cấp để mã chưa khai báo module vẫn có thể chạy trong hệ sinh thái JPMS. Trong cách chạy phổ biến, các class và JAR đặt trên **classpath** thuộc unnamed module của class loader tương ứng.

Ví dụ:

```bash
javac -d out src/com/example/Main.java
java -cp out com.example.Main
```

Hoặc:

```bash
java -classpath "out;lib/example.jar" com.example.Main
```

Trong ví dụ Windows thứ hai, dấu chấm phẩy phân cách các mục classpath. Trên Linux/macOS, ký tự phân cách là dấu hai chấm.

### 3.1. Unnamed module không có tên

Không có tên module để ghi trong một chỉ thị `requires`. Vì vậy, module khác không thể viết:

```java
module com.acme.app {
    // Không có tên hợp lệ để requires unnamed module.
}
```

Khi kiểm tra module của một class:

```java
Module module = Main.class.getModule();
System.out.println(module.getName());
```

Nếu class thuộc unnamed module, `getName()` trả về `null`.

### 3.2. Unnamed module đọc mọi module quan sát được

Unnamed module có quy tắc readability rộng để hỗ trợ mã classpath:

- Nó đọc mọi module quan sát được trong môi trường tương ứng.
- Nó export mọi package thuộc unnamed module đó.
- Nó mở mọi package thuộc unnamed module đó cho reflection.

Nhưng có một bất đối xứng quan trọng: **named module không thể dùng `requires` để đọc unnamed module**. Không có tên module hợp lệ để viết trong descriptor, và các compilation unit của unnamed module không hiển thị như dependency thông thường cho named module.

Ví dụ, một ứng dụng cũ chạy trên classpath có thể gọi API được export của một named module khi module đó có mặt và được đưa vào module graph. Ngược lại, một named module không thể chỉ ghi `requires` để dùng một thư viện vẫn nằm trên classpath.

Đây là khác biệt quan trọng khi chuyển ứng dụng từ classpath sang module path.

### 3.3. Unnamed module không đồng nghĩa unnamed package

Hai khái niệm này rất dễ nhầm:

- **Unnamed package:** Một file Java không có khai báo `package`.
- **Unnamed module:** Một module không có tên, thường chứa các lớp từ classpath.

Một class thuộc package có tên như `com.example.service` vẫn có thể thuộc unnamed module nếu được nạp từ classpath. Vì vậy, “module không tên” không có nghĩa toàn bộ class bên trong phải bỏ khai báo package.

### 3.4. Unnamed module và reflection

Các package của unnamed module được xem là export và open. Điều này tạo khả năng tương thích cao với thư viện cũ dùng reflection. Tuy nhiên, không nên suy ra rằng một named module cũng có quyền truy cập sâu tương tự vào mọi package của các named module khác.

Đối với named module, quyền reflection vẫn chịu kiểm soát bởi `opens` hoặc khai báo `open module`. Đây là một phần của cơ chế đóng gói mạnh.

## 4. Automatic module: JAR cũ được đặt trên module path

Một JAR có thể chưa chứa `module-info.class` nhưng vẫn được dùng trên module path. Trong trường hợp này, Java tạo một **automatic module**.

Automatic module là named module được khai báo ngầm. Nó giúp thư viện chưa chuyển sang JPMS có thể tham gia module graph, để các named module khác có thể khai báo `requires` đến nó.

### 4.1. Một JAR trở thành automatic module khi nào?

Quy tắc nhận diện cơ bản của Java 17:

| Vị trí JAR | Trạng thái |
|---|---|
| Trên classpath | Các lớp thuộc unnamed module |
| Trên module path, có module descriptor | Explicit named module |
| Trên module path, không có module descriptor | Automatic module |

Điều đó có nghĩa **cùng một file JAR không có module descriptor** có thể thuộc unnamed module hoặc automatic module tùy cách chạy:

```bash
# JAR được xem như classpath dependency
java -cp "app-classes;lib/legacy-json-2.4.1.jar" com.acme.Main

# JAR được xem như automatic module
java --module-path "mods;lib/legacy-json-2.4.1.jar" \
     --module com.acme.app/com.acme.Main
```

Ví dụ lệnh trên dùng dấu chấm phẩy theo Windows. Trên Linux/macOS, thay bằng dấu hai chấm.

### 4.2. Đặt tên cho automatic module

Tên module được xác định theo thứ tự:

1. Nếu manifest của JAR có thuộc tính `Automatic-Module-Name` trong phần main attributes, dùng giá trị đó.
2. Nếu không có, hệ thống suy ra tên từ tên file JAR.

Ví dụ manifest:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacyjson
```

Với manifest này, module name là `com.acme.legacyjson` dù file có thể được đặt tên `legacy-json-2.4.1.jar`.

Nếu không có thuộc tính trên, Java 17 xử lý tên file theo các bước chính:

- Bỏ hậu tố `.jar`.
- Nếu có phần phiên bản nhận diện được sau dấu gạch ngang, tách phần phiên bản ra khỏi tên module.
- Thay các ký tự không phải chữ/số ASCII bằng dấu chấm.
- Gộp nhiều dấu chấm liên tiếp thành một dấu chấm.
- Bỏ dấu chấm ở đầu và cuối.

Ví dụ:

| Tên file JAR | Tên automatic module suy ra |
|---|---|
| `foo-bar.jar` | `foo.bar` |
| `legacy-json-2.4.1.jar` | `legacy.json` |
| `acme-client-3.0.jar` | `acme.client` |

Tên file có thể đổi khi nâng phiên bản thư viện. Vì vậy, với thư viện muốn hỗ trợ người dùng JPMS trong giai đoạn chuyển đổi, tác giả nên khai báo `Automatic-Module-Name` ổn định trong manifest. Điều này giúp tên module không phụ thuộc tên file và số phiên bản.

### 4.3. Automatic module có những quyền gì?

Automatic module có các đặc điểm quan trọng:

- Có tên và tham gia module graph như một named module.
- Đọc tất cả module khác trong cấu hình, bao gồm các unnamed module.
- Tất cả package của nó được xem là exported.
- Tất cả package của nó cũng được xem là opened cho reflection.
- Không có module descriptor tường minh để tác giả khai báo từng `requires`, `exports` hay `opens` như explicit named module.

Điểm “đọc mọi module” khiến automatic module dễ kết nối với thư viện cũ. Điểm “export/open mọi package” giúp các client tiếp tục truy cập API và reflection mà không cần tác giả JAR thiết kế module descriptor ngay lập tức.

Tuy nhiên, quyền rộng này cũng có nghĩa automatic module chưa cung cấp mức đóng gói mạnh và ranh giới API rõ ràng như explicit named module.

### 4.4. Dùng automatic module từ một named module

Giả sử JAR `legacy-json-2.4.1.jar` không có `module-info.class` và manifest không có `Automatic-Module-Name`. Module name được suy ra là `legacy.json`.

Named module có thể khai báo:

```java
module com.acme.application {
    requires legacy.json;
}
```

Sau đó code có thể import các kiểu public trong package của JAR, vì automatic module export tất cả package.

Điều cần nhớ là tên `legacy.json` là tên module, không nhất thiết là tên package Java mà thư viện sử dụng. Module name và package name là hai hệ thống tên riêng.

### 4.5. Automatic module vẫn chịu kiểm tra xung đột module

Automatic module không loại bỏ các quy tắc của module graph. Ví dụ:

- Hai JAR suy ra cùng module name có thể gây xung đột khi được tìm thấy cùng lúc.
- Các package bị split giữa những module mà một module đọc có thể khiến việc resolve thất bại.
- Tên module suy ra từ file có thể thay đổi nếu đổi cách đặt tên JAR.

Đừng dùng automatic module như một cách để bỏ qua việc tổ chức dependency. Hãy kiểm tra tên module, package và đồ thị phụ thuộc của ứng dụng.

## 5. So sánh ba loại module

| Tiêu chí | Named module tường minh | Unnamed module | Automatic module |
|---|---|---|---|
| Có tên module? | Có | Không | Có |
| Descriptor | Có `module-info.java`/`module-info.class` | Không | Descriptor được suy ra |
| Thường xuất hiện từ | Mã module hoặc modular JAR | Lớp/JAR trên classpath | JAR không modular trên module path |
| Khai báo dependency bằng `requires` | Có | Không | Không có descriptor tường minh để khai báo |
| Readability | Theo module graph và `requires` | Đọc mọi module quan sát được | Đọc tất cả module trong cấu hình |
| Package được export | Theo `exports` | Tất cả package của module | Tất cả package |
| Package được open cho reflection | Theo `opens`/`open module` | Tất cả package | Tất cả package |
| Đóng gói mạnh | Có thể kiểm soát rõ | Không có ranh giới package chặt như explicit module | Rộng, tương thích nhưng ít kiểm soát |
| Vai trò phổ biến | Ứng dụng/thư viện đã modular hóa | Mã chạy trên classpath | Cầu nối cho JAR chưa modular hóa |

Sơ đồ nhận diện:

```text
classpath
   |
   v
unnamed module
   - không tên
   - đọc mọi module quan sát được
   - export/open mọi package của nó

module path
   |
   +--> JAR có module-info.class
   |       |
   |       v
   |    explicit named module
   |       - descriptor do tác giả khai báo
   |       - requires/exports/opens rõ ràng
   |
   +--> JAR không có module descriptor
           |
           v
        automatic module
           - có tên suy ra hoặc lấy từ manifest
           - đọc tất cả module
           - export/open mọi package
```

## 6. Readability và khả năng truy cập package là hai điều kiện riêng

Một lỗi phổ biến khi mới học JPMS là nghĩ rằng chỉ cần module A khai báo `requires B` thì A có thể truy cập mọi class trong B.

Thực tế, để code của module A tham chiếu một kiểu từ module B, thường phải thỏa cả hai điều kiện:

1. **Readability:** A đọc B, trực tiếp hoặc thông qua quan hệ được quy định bởi module graph.
2. **Accessibility:** Package chứa kiểu đó được B export cho A, và kiểu/thành viên đáp ứng quy tắc truy cập Java.

Ví dụ:

```java
module com.acme.orders {
    exports com.acme.orders.api;
}

module com.acme.web {
    requires com.acme.orders;
}
```

Code trong `com.acme.web` có thể sử dụng public API thuộc `com.acme.orders.api`. Nhưng nó không thể tham chiếu một class ở `com.acme.orders.internal` nếu package đó không được export.

### 6.1. requires transitive

`requires transitive` có nghĩa module hiện tại yêu cầu module đích, đồng thời chuyển tiếp readability đó đến module phụ thuộc vào nó.

Ví dụ:

```java
module com.acme.orders {
    requires transitive com.acme.money;
}

module com.acme.web {
    requires com.acme.orders;
}
```

Trong trường hợp này, `com.acme.web` đọc `com.acme.money` thông qua quan hệ transitive của `com.acme.orders`. Điều này hữu ích nếu API public của orders để lộ kiểu thuộc money và người dùng orders cần đọc kiểu đó.

Không nên thêm `transitive` cho mọi dependency. Nó làm dependency trở thành một phần của hợp đồng sử dụng module và có thể khiến đồ thị phụ thuộc của client rộng hơn dự kiến.

### 6.2. requires static

`requires static` biểu thị dependency bắt buộc khi biên dịch nhưng có thể không hiện diện ở runtime:

```java
module com.acme.library {
    requires static com.acme.optional.annotations;
}
```

Nó phù hợp với dependency chỉ cần trong một số tình huống compile-time, ví dụ annotation hoặc API tùy chọn. Code cần bảo đảm không gọi class của dependency đó trong đường chạy mà module không có mặt.

### 6.3. Named module không đọc unnamed module

Điểm bất đối xứng cần nhớ:

- Unnamed module đọc mọi module quan sát được.
- Automatic module đọc tất cả module trong cấu hình, bao gồm unnamed module.
- Named module tường minh không thể khai báo `requires` đến unnamed module.

Do đó, nếu một named module cần dùng thư viện đang nằm trên classpath, hãy đưa thư viện đó vào module path (nếu có thể dùng như automatic module) hoặc chuyển thư viện thành named module. Đừng dựa vào việc named module sẽ tự nhìn thấy mọi class trên classpath.

## 7. Ví dụ cấu trúc dự án có hai named module

Một dự án nhỏ có module API và module ứng dụng:

```text
src/
  com.acme.greeting/
    module-info.java
    com/acme/greeting/api/Greeter.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
```

Module thư viện:

```java
module com.acme.greeting {
    exports com.acme.greeting.api;
}
```

Class API:

```java
package com.acme.greeting.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Module ứng dụng:

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

Class main:

```java
package com.acme.app;

import com.acme.greeting.api.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("Java 17"));
    }
}
```

Biên dịch các module từ source root:

```bash
javac --module-source-path src -d mods -m com.acme.greeting,com.acme.app
```

Chạy module ứng dụng:

```bash
java --module-path mods -m com.acme.app/com.acme.app.Main
```

Kết quả:

```text
Hello, Java 17
```

Trong lệnh chạy:

- `--module-path mods` chỉ ra nơi tìm các module.
- `-m` (hoặc `--module`) chọn module và class main theo dạng `module/class`.
- Module app đọc module greeting vì descriptor khai báo `requires`.
- Package API truy cập được vì greeting khai báo `exports`.

## 8. Ví dụ dùng thư viện chưa có module descriptor như automatic module

Giả sử ứng dụng có JAR `legacy-json-2.4.1.jar`. JAR không có `module-info.class`. Nếu đặt nó trên module path và không có manifest attribute `Automatic-Module-Name`, tên suy ra theo quy tắc Java 17 là `legacy.json`.

Module descriptor của ứng dụng có thể viết:

```java
module com.acme.application {
    requires legacy.json;
}
```

Sau đó code có thể import các kiểu public trong package của JAR, vì automatic module export tất cả package.

Biên dịch và chạy cần đưa cả output module và JAR vào module path:

```bash
javac --module-path lib --module-source-path src -d mods -m com.acme.application
java --module-path "mods;lib/legacy-json-2.4.1.jar" \
     -m com.acme.application/com.acme.application.Main
```

Nếu ứng dụng chạy trên Windows, dùng dấu chấm phẩy để phân cách các path. Trên Linux/macOS, dùng dấu hai chấm.

Ví dụ này minh họa cơ chế module; tên package và class thực tế cần lấy từ API của thư viện đang dùng. Không được giả định mọi JAR không modular đều có thể dùng ngay trên module path: JAR phải đáp ứng các điều kiện để tạo automatic module, chẳng hạn không chứa class ở unnamed package và tên module phải hợp lệ.

## 9. Lộ trình chuyển từ classpath sang JPMS

Automatic module và unnamed module hỗ trợ một quá trình chuyển đổi từng bước.

### Bước 1 — Ứng dụng vẫn chạy trên classpath

Các lớp ứng dụng và dependency trên classpath thuộc unnamed module. Mã chưa cần có `module-info.java`.

### Bước 2 — Đưa một số thư viện lên module path

Các JAR đã có module descriptor trở thành explicit named module. JAR chưa có descriptor trở thành automatic module. Ứng dụng classpath có thể tương tác với các module mà nó đọc và các package được export.

### Bước 3 — Chuyển ứng dụng thành named module

Thêm `module-info.java`, khai báo `requires` đến các dependency cần thiết. Dependency còn nằm trên classpath sẽ thuộc unnamed module và không thể được named module đọc bằng `requires`.

### Bước 4 — Chuyển các dependency automatic sang explicit module khi có thể

Khi tác giả thư viện cung cấp module descriptor rõ ràng, ứng dụng có thể dùng các package được export theo API được công bố. Module descriptor cũng giúp xác định dependency và giới hạn reflection tốt hơn.

### Bước 5 — Thu hẹp API và quyền reflection

Chỉ export package cần công khai; mở package cho framework đúng nơi cần thiết. Việc này giúp ranh giới module rõ hơn và giảm phụ thuộc vào implementation details.

Sơ đồ:

```text
Tất cả chạy trên classpath
          |
          v
Đưa dependency modular lên module path
          |
          v
JAR cũ trở thành automatic module
          |
          v
Ứng dụng có module-info.java
          |
          v
Thư viện lần lượt có explicit module descriptor
          |
          v
Đồ thị module và API được kiểm soát rõ
```

Automatic module vẫn là một cơ chế hợp lệ của JPMS, không phải cú pháp lỗi thời. Tuy nhiên, JLS cảnh báo rằng tên và tập package export của automatic module có thể thay đổi khi tác giả chuyển nó thành explicit module. Vì vậy, không nên xây một API lâu dài phụ thuộc quá sâu vào tên và quyền export rộng của automatic module.

## 10. Kiểm tra một class thuộc loại module nào

Java Reflection API cho phép xem module của class:

```java
public class ModuleIdentityDemo {
    public static void main(String[] args) {
        Module module = ModuleIdentityDemo.class.getModule();

        System.out.println("name = " + module.getName());
        System.out.println("descriptor = " + module.getDescriptor());
        System.out.println("named = " + module.isNamed());
    }
}
```

Diễn giải:

- Với class trong unnamed module, `getName()` trả về `null` và `isNamed()` là `false`.
- Với explicit named module, `getName()` trả tên module; descriptor phản ánh khai báo tường minh.
- Với automatic module, `getName()` trả tên automatic module; descriptor có thể được kiểm tra để biết đó là automatic descriptor.

Có thể kiểm tra descriptor:

```java
import java.lang.module.ModuleDescriptor;

ModuleDescriptor descriptor = module.getDescriptor();
if (descriptor != null && descriptor.isAutomatic()) {
    System.out.println("This class belongs to an automatic module");
}
```

Đối với unnamed module, descriptor có thể là `null` vì module này không có module descriptor tường minh.

## 11. Các lỗi thường gặp khi làm việc với ba loại module

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Named module không tìm thấy class của dependency trên classpath | Named module không đọc unnamed module | Đưa dependency lên module path hoặc modular hóa dependency |
| Đã khai báo `requires` nhưng vẫn không import được class | Package chứa class chưa được export hoặc kiểu không accessible | Kiểm tra `exports` và modifier của kiểu/thành viên |
| Framework không truy cập được field private qua reflection | Package chưa được mở | Dùng `opens package to framework.module` hoặc `open module` khi thực sự cần |
| `requires legacy-json` không tìm thấy module | Tên suy ra từ JAR không như dự kiến hoặc JAR nằm sai path | Kiểm tra `Automatic-Module-Name` và tên file, dùng công cụ module để xem module path |
| Cùng dependency chạy được trên classpath nhưng lỗi trên module path | Ranh giới module, package hoặc split package được áp dụng | Kiểm tra module descriptor, package và dependency graph |
| Hai thư viện tạo cùng module name | Manifest hoặc tên JAR suy ra trùng nhau | Chọn phiên bản/phân phối có tên module duy nhất |
| Hai module mà ứng dụng đọc cùng export một package | Split package gây xung đột trong module graph | Tổ chức lại package hoặc chọn một nguồn sở hữu package |
| Tưởng package có tên thì module cũng có tên | Nhầm package với module | Kiểm tra `Class.getModule()`; package có tên vẫn có thể nằm trong unnamed module |
| Automatic module bị coi là explicit module | JAR không có descriptor nhưng được đặt trên module path | Xem `ModuleDescriptor.isAutomatic()` và cung cấp descriptor khi cần kiểm soát rõ |

## 12. Nguyên tắc thiết kế nên áp dụng

- Dùng named module tường minh cho ứng dụng và thư viện cần công bố dependency/API rõ ràng.
- Giữ package nội bộ không export nếu client không cần truy cập.
- Dùng `opens` có phạm vi cụ thể cho framework cần reflection sâu; tránh mở tất cả package khi không cần.
- Đừng đặt một thư viện lên classpath rồi mong named module có thể `requires` nó.
- Với JAR chưa modular hóa cần dùng trên module path, kiểm tra tên automatic module và ưu tiên thuộc tính `Automatic-Module-Name` ổn định do nhà cung cấp công bố.
- Không dựa vào việc automatic module export/open tất cả package như một hợp đồng API lâu dài.
- Phân biệt việc module đọc được module khác với việc package của module đó được export.
- Khi di chuyển ứng dụng, thay đổi từng bước và ghi lại cấu hình module path, classpath cùng module descriptor.

## 13. Bài tập thực hành

### Bài 1 — Nhận diện module theo cách chạy

Một JAR `payment-client-2.1.jar` không có `module-info.class` và không có `Automatic-Module-Name`.

1. Nếu chạy với `-cp payment-client-2.1.jar`, các lớp thuộc loại module nào?
2. Nếu đặt JAR trên `--module-path`, nó thuộc loại module nào?
3. Tên automatic module được suy ra là gì?

**Gợi ý:** Trên classpath, lớp thuộc unnamed module. Trên module path, JAR trở thành automatic module. Tên suy ra là `payment.client`.

### Bài 2 — Đọc module descriptor

Cho:

```java
module com.acme.web {
    requires com.acme.orders;
    exports com.acme.web.api;
    opens com.acme.web.dto to com.fasterxml.jackson.databind;
}
```

Giải thích:

- Vì sao `com.acme.web` có thể tham chiếu kiểu được export bởi `com.acme.orders`?
- Package nào là API công khai của web?
- Vì sao package DTO được mở cho Jackson?
- Jackson có được phép dùng package DTO như API compile-time thông thường chỉ nhờ `opens` không?

**Gợi ý:** `requires` tạo readability; package của orders cần export. `exports` công khai API web. `opens` cấp quyền reflection runtime, không thay thế `exports`.

### Bài 3 — Phát hiện dependency trên classpath

Ứng dụng `com.acme.app` là named module. Một thư viện `legacy-utils.jar` không có module descriptor và vẫn nằm trong classpath.

Vì sao khai báo `requires legacy.utils;` không thể làm ứng dụng đọc thư viện này? Nêu hai hướng xử lý.

**Gợi ý:** JAR trên classpath thuộc unnamed module và không có tên để `requires`. Có thể chuyển JAR lên module path để nó thành automatic module, hoặc chuyển thư viện thành explicit named module.

### Bài 4 — Phân biệt exports và opens

Một package có class public và field private. Framework serialization cần đọc/ghi field private bằng reflection.

- `exports` có đủ để cấp quyền reflection sâu vào field private không?
- `opens` có cho code client import class ở compile time không?
- Hãy viết một chỉ thị `opens` có giới hạn cho module framework.

**Gợi ý:** `exports` không cấp reflection sâu vào thành viên private. `opens` cho reflection runtime nhưng không thay quyền truy cập compile-time. Ví dụ: `opens com.acme.model to com.example.serializer;`.

### Bài 5 — Đặt tên automatic module ổn định

Thư viện có file `search-engine-4.5.0.jar`. Nếu không có manifest attribute, tên module được suy ra từ tên file. Hãy viết main manifest attribute để công bố tên ổn định `com.acme.search` và giải thích lợi ích khi nâng phiên bản JAR.

### Bài 6 — Kiểm tra module của class

Viết một chương trình in:

- `Class.getModule().getName()`
- `Class.getModule().isNamed()`
- `Class.getModule().getDescriptor()`

Chạy class một lần trên classpath và một lần từ automatic module. Quan sát sự khác nhau của tên và descriptor.

## 14. Tài liệu chính thức của Java 17

- [Java Language Specification 17 — Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): module declaration, dependency, exports/opens và unnamed modules.
- [Java SE 17 API — java.lang.module package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): module resolution, readability graph và cách xử lý automatic modules.
- [Java SE 17 API — ModuleFinder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html): cách tìm modular JAR, automatic module và quy tắc suy ra tên từ manifest/tên file.
- [Java SE 17 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): mô tả module, trạng thái automatic và các directive.
- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): kiểm tra module, tên module, export và open ở runtime.
- [Dev.java — Code on the Class Path: The Unnamed Module](https://dev.java/learn/modules/unnamed-module/): mô tả unnamed module trong quá trình tương tác với JPMS.
- [Dev.java — Incremental Modularization with Automatic Modules](https://dev.java/learn/modules/automatic-module/): cách dùng automatic module trong quá trình chuyển thư viện sang module path.

**Ghi nhớ:** Named module có descriptor tường minh và kiểm soát dependency cùng package được công khai. Unnamed module không có tên, thường chứa code trên classpath; nó đọc các module quan sát được nhưng named module không thể khai báo `requires` đến nó. Automatic module là named module được tạo từ JAR không modular trên module path; nó có tên suy ra hoặc lấy từ manifest, đọc tất cả module và export/open tất cả package. Hiểu rõ ba loại này giúp tổ chức module path, classpath và ranh giới đóng gói mạnh đúng cách trong Java 17.
