# API `public` nhưng không `exports` vẫn bị giới hạn trong Java Module System

## 1. Mục tiêu

Trong Java Platform Module System (JPMS, từ Java 9), một lớp được khai báo `public` **chưa chắc** có thể được module khác sử dụng. Khi một ứng dụng chạy dưới dạng **named modules**, khả năng truy cập một kiểu từ bên ngoài phụ thuộc đồng thời vào phạm vi truy cập của Java, quan hệ đọc giữa các module và việc package chứa kiểu đó có được xuất ra hay không.

Sau bài này, bạn có thể:

- Giải thích vì sao một lớp `public` vẫn báo lỗi khi được `import` từ module khác.
- Phân biệt `public`, `requires`, `exports`, `exports ... to` và `opens`.
- Tạo một ví dụ gồm module thư viện và module ứng dụng để quan sát cơ chế đóng gói.
- Nhận biết lỗi khi biên dịch, lỗi truy cập lúc chạy và lỗi truy cập qua reflection.
- Thiết kế API công khai của module mà không vô tình làm lộ package nội bộ.

## 2. Ba điều kiện để module khác gọi được API

Giả sử lớp `com.acme.engine.internal.MathCore` nằm trong module `acme.engine` và lớp gọi nằm trong module `acme.app`. Với lệnh gọi thông thường ở mã nguồn Java, cần xét ba lớp kiểm soát:

1. **Ngôn ngữ Java:** kiểu và thành viên phải có mức truy cập phù hợp. `public` cho phép truy cập theo quy tắc ngôn ngữ, nhưng chỉ là một điều kiện.
2. **Khả năng đọc module (readability):** module gọi phải đọc được module cung cấp; ví dụ `acme.app` khai báo `requires acme.engine;`.
3. **Package được export:** `acme.engine` phải có `exports com.acme.engine.internal;`, hoặc một qualified export dành riêng cho `acme.app`.

Chỉ cần thiếu điều kiện thứ ba, `public class MathCore` vẫn không thể được truy cập trực tiếp từ `acme.app`.

> Quy tắc ghi nhớ: **`public` mở quyền trong phạm vi luật truy cập của Java; `exports` quyết định package có thuộc API nhìn thấy được từ bên ngoài module hay không.**

`exports` là cơ chế ở **cấp package**, không phải ở cấp từng lớp. Export một package không tự động biến các lớp package-private hay thành viên `private` thành công khai.

## 3. Ví dụ thực hành: lớp public trong package không export

Cấu trúc dự án:

~~~text
src/
├── acme.engine/
│   ├── module-info.java
│   └── com/acme/engine/
│       ├── api/Calculator.java
│       └── internal/MathCore.java
└── acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

**Module thư viện — `src/acme.engine/module-info.java`:**

~~~java
module acme.engine {
    exports com.acme.engine.api;
    // Không exports com.acme.engine.internal
}
~~~

**API được xuất — `src/acme.engine/com/acme/engine/api/Calculator.java`:**

~~~java
package com.acme.engine.api;

import com.acme.engine.internal.MathCore;

public final class Calculator {
    private Calculator() {}

    public static int twice(int value) {
        return MathCore.twice(value);
    }
}
~~~

**Phần triển khai nội bộ — `src/acme.engine/com/acme/engine/internal/MathCore.java`:**

~~~java
package com.acme.engine.internal;

public final class MathCore {
    private MathCore() {}

    public static int twice(int value) {
        return value * 2;
    }
}
~~~

Chú ý: `MathCore` và phương thức `twice` đều là `public`. Tuy vậy, package `com.acme.engine.internal` không được liệt kê trong các câu lệnh `exports`. `Calculator` vẫn được phép gọi `MathCore`, vì hai lớp **cùng một module**.

**Module ứng dụng — `src/acme.app/module-info.java`:**

~~~java
module acme.app {
    requires acme.engine;
}
~~~

**Ứng dụng dùng API hợp lệ — `src/acme.app/com/acme/app/Main.java`:**

~~~java
package com.acme.app;

import com.acme.engine.api.Calculator;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Calculator.twice(21));
    }
}
~~~

Biên dịch từ thư mục gốc dự án rồi chạy:

~~~shell
javac -d out --module-source-path src -m acme.engine,acme.app
java --module-path out --module acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
42
~~~

Giờ thử sửa `Main.java` để truy cập `MathCore` trực tiếp:

~~~java
import com.acme.engine.internal.MathCore;

// Trong main:
System.out.println(MathCore.twice(21));
~~~

Đoạn sửa **không biên dịch được** vì package `com.acme.engine.internal` không được `acme.engine` export tới `acme.app`. Chẩn đoán thường có dạng:

~~~text
package com.acme.engine.internal is not visible
(package com.acme.engine.internal is declared in module acme.engine,
 which does not export it)
~~~

Dù `acme.app` đã có `requires acme.engine` và `MathCore` là `public`, ứng dụng vẫn không có quyền truy cập package nội bộ. Đây là tính năng **strong encapsulation** của named modules.

## 4. Phân biệt `public`, `requires` và `exports`

| Khai báo | Đặt ở đâu? | Ý nghĩa |
|---|---|---|
| `public class X` | Lớp Java | Cho phép truy cập kiểu theo quy tắc ngôn ngữ, nếu đường đi qua ranh giới module cũng hợp lệ |
| `public void run()` | Thành viên Java | Cho phép truy cập phương thức nếu bản thân kiểu chứa nó có thể truy cập và các điều kiện khác thỏa mãn |
| `requires acme.engine;` | `module-info.java` của module sử dụng | Tạo quan hệ đọc module `acme.engine` |
| `exports com.acme.engine.api;` | `module-info.java` của module cung cấp | Export package cho những module đọc được module cung cấp |
| `exports com.acme.engine.internal to acme.debug;` | `module-info.java` của module cung cấp | Chỉ export package đó đến module `acme.debug` |
| `opens com.acme.engine.internal;` | `module-info.java` của module cung cấp | Cho phép truy cập phản chiếu tại runtime theo quy tắc `opens`; không cấp quyền `import` trong mã nguồn |

Cần phân biệt hai tình huống:

- **Cùng named module:** lớp trong một package không export vẫn có thể được mã trong các package khác của **chính module đó** sử dụng, miễn quy tắc `public`/`protected`/package-private/`private` cho phép.
- **Khác named module:** package phải được export tới module gọi, đồng thời module gọi phải đọc được module cung cấp. `requires` đơn lẻ không thay thế `exports`.

Ví dụ `exports com.acme.engine.api;` không có nghĩa toàn bộ các package nằm dưới tiền tố `com.acme.engine` đều được export. `com.acme.engine.internal` là một package khác và vẫn được đóng.

## 5. Khi nào nên dùng `exports ... to`?

Một thư viện có thể cần mở package kỹ thuật cho đúng một module tích hợp đã biết, trong khi giữ kín package đó với phần còn lại:

~~~java
module acme.engine {
    exports com.acme.engine.api;
    exports com.acme.engine.internal to acme.debug;
}
~~~

Khi đó:

- `acme.debug` có thể sử dụng những kiểu `public` thuộc `com.acme.engine.internal` nếu nó đọc `acme.engine`.
- `acme.app` không tự động được quyền đó.
- Việc export theo tên module là một ngoại lệ có chủ đích; thay đổi tên module nhận quyền phải cập nhật lại khai báo.

Nên ưu tiên API ổn định trong một package `api` được export rộng rãi. Qualified exports hữu ích khi phải thiết kế giao tiếp riêng giữa những module kiểm soát được, không nên dùng để xuất bừa mọi package nội bộ.

## 6. `opens` có thay thế `exports` không?

**Không.** `exports` và `opens` phục vụ hai trường hợp khác nhau.

~~~java
module acme.engine {
    exports com.acme.engine.api;
    opens com.acme.engine.internal;
}
~~~

- `exports` cho phép **truy cập thông thường** đến kiểu và thành viên có mức truy cập thích hợp trong package được export, bao gồm kiểm tra tại compile time và runtime.
- `opens` cho phép **truy cập qua reflection tại runtime**, bao gồm deep reflection khi API phản chiếu yêu cầu mở package. Nó **không** làm cho câu lệnh `import com.acme.engine.internal.MathCore;` ở module khác trở nên hợp lệ.
- `opens p to other.module;` giới hạn quyền mở cho module có tên `other.module`.
- `open module acme.engine { ... }` mở các package của module cho reflection ở runtime, nhưng không đồng nghĩa export tất cả package cho truy cập thông thường.

Đối với framework cần reflection để đọc hoặc ghi những thành viên không công khai, có thể phải cấu hình `opens`; đối với mã nguồn muốn gọi một lớp từ module khác, hãy kiểm tra `requires` và `exports`.

### Ví dụ kiểm tra ranh giới module bằng API runtime

Từ `Main`, vì `Calculator` nằm trong package API được export, ta có thể lấy thông tin module và hỏi xem package nội bộ có được export hay mở cho module ứng dụng không:

~~~java
Module library = Calculator.class.getModule();
Module consumer = Main.class.getModule();

System.out.println(
    library.isExported("com.acme.engine.internal", consumer)
);
System.out.println(
    library.isOpen("com.acme.engine.internal", consumer)
);
~~~

Với `module-info.java` ban đầu ở mục 3, cả hai kết quả là `false`. Đó là kiểm tra **quan hệ cụ thể giữa hai module**, không phải đoán quyền truy cập dựa trên từ khóa `public` trong file Java.

## 7. Cần hiểu đúng các lỗi thường gặp

**Lỗi compile time: `package ... is not visible`.** Đây là dấu hiệu thường gặp khi package thuộc một named module nhưng không được export cho module gọi. Kiểm tra khai báo `exports` ở module cung cấp và `requires` ở module sử dụng.

**Lỗi compile time: `module not found`.** Khác với package không được export: ở đây Java không tìm thấy module theo module path hoặc cấu hình build. Hãy kiểm tra tên module và `--module-path`.

**Lỗi runtime: `IllegalAccessError`.** Có thể xảy ra khi bytecode tham chiếu tới lớp/thành viên không còn được module export hợp lệ lúc chạy, chẳng hạn cấu hình compile time và runtime khác nhau. Không nên xem việc biên dịch thành công trong một cấu hình là bằng chứng rằng mọi cấu hình runtime đều đúng.

**Lỗi reflection: `InaccessibleObjectException`.** Thường xuất hiện khi ứng dụng cố dùng deep reflection, ví dụ `setAccessible(true)`, đối với package chưa được mở phù hợp. Kiểm tra `opens`/`--add-opens` thay vì chỉ thêm `exports`.

**Lỗi reflection: `IllegalAccessException`.** Có thể xuất hiện khi lời gọi phản chiếu tới kiểu hoặc thành viên không thể truy cập theo các quy tắc liên quan. Reflection không phải lối tắt mặc định để vượt qua tính đóng gói của named modules.

## 8. `--add-exports` và `--add-opens`: công cụ ngoại lệ

Đôi khi một ứng dụng cũ hoặc công cụ kiểm thử cần tạm thời tiếp cận package không export. JVM và compiler có hỗ trợ tùy chọn bổ sung quyền trong một lần chạy hoặc biên dịch.

Ví dụ cho phép `acme.app` truy cập trực tiếp package nội bộ:

~~~shell
javac --add-exports acme.engine/com.acme.engine.internal=acme.app -d out --module-source-path src -m acme.engine,acme.app
java --add-exports acme.engine/com.acme.engine.internal=acme.app --module-path out --module acme.app/com.acme.app.Main
~~~

Đây là **ngoại lệ do cấu hình**. Khi mã nguồn `acme.app` thật sự tham chiếu trực tiếp tới `MathCore`, cần đảm bảo cấu hình thích hợp ở cả giai đoạn biên dịch và chạy.

Với reflection, tùy chọn tương ứng ở runtime có dạng:

~~~shell
java --add-opens acme.engine/com.acme.engine.internal=acme.app --module-path out --module acme.app/com.acme.app.Main
~~~

`--add-opens` phục vụ truy cập phản chiếu; nó không biến package thành API được phép `import` ở compile time.

Dùng các tùy chọn này cho di trú, chẩn đoán hoặc kiểm thử có kiểm soát. Nếu mã ứng dụng phụ thuộc lâu dài vào package nội bộ của thư viện, nên sửa thiết kế API hoặc module thay vì coi cờ dòng lệnh là hợp đồng ổn định.

## 9. Tránh làm lộ kiểu nội bộ trong API đã export

Dù `com.acme.engine.api` được export, thiết kế sau vẫn khó dùng từ module khác:

~~~java
package com.acme.engine.api;

import com.acme.engine.internal.MathCore;

public class EngineFactory {
    public MathCore create() {
        // Ví dụ minh họa kiểu trả về:
        return null;
    }
}
~~~

`EngineFactory` có thể truy cập được, nhưng chữ ký `create()` lại chứa kiểu `MathCore` ở package không export. Khách hàng bên ngoài có thể vướng lỗi truy cập kiểu khi biên dịch hoặc sử dụng API. Việc có `public` trong chữ ký không làm kiểu đó tự động được export.

Hướng thiết kế tốt hơn là đặt một kiểu giao diện hoặc DTO ổn định trong package được export, để API trả về hoặc nhận vào **kiểu công khai thực sự**:

~~~java
// Package com.acme.engine.api
public interface Operation {
    int apply(int value);
}
~~~

~~~java
// Package com.acme.engine.api
public final class EngineFactory {
    private EngineFactory() {}

    public static Operation doubling() {
        return value -> value * 2;
    }
}
~~~

Ở đây client chỉ phụ thuộc `Operation` và `EngineFactory` trong package API. Chi tiết thuật toán có thể thay đổi bên trong module mà không buộc client phụ thuộc vào `internal`.

Các nguyên tắc áp dụng khi thiết kế module:

1. Export có chủ đích các package dùng làm hợp đồng công khai, thường chứa interface, DTO, facade hoặc lớp dịch vụ ổn định.
2. Để package triển khai nội bộ không export, kể cả khi lớp bên trong cần khai báo `public` để các package khác **cùng module** sử dụng.
3. Tránh đặt kiểu không export trong tham số, kiểu trả về hoặc superclass/interface của API hướng tới module khác.
4. Dùng `opens` cho nhu cầu reflection thực sự và cân nhắc `opens ... to` nếu chỉ một framework/module cần quyền đó.
5. Khi công bố thư viện, kiểm tra cả khả năng gọi từ một **module tiêu thụ độc lập**, không chỉ kiểm thử nội bộ của thư viện.

## 10. Kiểm tra module bằng công cụ JDK

Sau khi biên dịch thành công, có thể xem thông tin mô tả module:

~~~shell
java --module-path out --describe-module acme.engine
~~~

Hãy quan sát dòng package được export và các package được chứa trong module. Lệnh này giúp xác minh cấu hình module ở bản build đang kiểm tra; phần mô tả có thể khác đôi chút theo phiên bản JDK.

Khi gặp lỗi ở chương trình thực tế, thực hiện theo thứ tự:

1. Xác định mã gọi có đang thuộc một **named module** hay đang chạy trên classpath/unnamed module.
2. Xác định module sở hữu lớp; đối chiếu tên package chính xác.
3. Kiểm tra module gọi có đọc module sở hữu hay không (`requires` hoặc quan hệ readability tương ứng).
4. Kiểm tra package được `exports` cho module gọi hay chỉ `exports ... to` module khác.
5. Nếu dùng reflection, kiểm tra riêng `opens` và các tùy chọn runtime có liên quan.

Lưu ý: hành vi ứng dụng chạy thuần trên classpath khác với ứng dụng chạy bằng các named modules trên module path. Ví dụ trong bài cố ý đặt cả hai module trên module path để quan sát kiểm soát `exports` của JPMS.

## 11. Bài tập tự kiểm tra

**Bài 1.** Module `shop.core` chứa lớp `public class Inventory` ở package `shop.core.internal`. `shop.frontend` có `requires shop.core;` nhưng `shop.core` chỉ export `shop.core.api`. `shop.frontend` có thể `import shop.core.internal.Inventory` không?

**Đáp án:** Không. `Inventory` là `public` nhưng package chứa nó không export tới `shop.frontend`.

**Bài 2.** Thêm `opens shop.core.internal;` có giúp câu lệnh `import` ở bài 1 biên dịch không?

**Đáp án:** Không. `opens` giải quyết truy cập reflection tại runtime; import thông thường cần package được `exports` thích hợp.

**Bài 3.** Nếu thêm `exports shop.core.internal to shop.admin;`, `shop.frontend` có sử dụng được `Inventory` không?

**Đáp án:** Không, vì quyền export giới hạn cho `shop.admin`. Module `shop.admin` cũng phải đọc được `shop.core` và tuân thủ quy tắc truy cập Java.

**Bài 4.** Bên trong `shop.core`, lớp `shop.core.api.InventoryService` có thể gọi `public` method của `shop.core.internal.Inventory` khi package `internal` không export không?

**Đáp án:** Có, nếu mức truy cập Java bình thường thỏa mãn. Cơ chế `exports` kiểm soát truy cập **từ module khác**, không ngăn các package trong cùng module sử dụng lớp `public` của nhau.

## 12. Ghi nhớ

- `public` chỉ là phạm vi truy cập trong ngôn ngữ Java; với named modules, khả năng truy cập từ bên ngoài còn phụ thuộc **readability** và **exports**.
- `requires` cho phép một module đọc module khác; `exports` cho phép package được truy cập qua biên giới module.
- Một lớp `public` trong package không export vẫn có thể là **chi tiết triển khai nội bộ** của module.
- `opens` phục vụ reflection ở runtime, còn `exports` phục vụ truy cập thông thường; chúng không hoán đổi cho nhau.
- Thiết kế API tốt là export bề mặt ổn định và giữ phần triển khai nội bộ được đóng gói.
