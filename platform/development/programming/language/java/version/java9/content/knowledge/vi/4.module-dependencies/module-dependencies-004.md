# Kết hợp `static` với `transitive` đúng mục đích trong JPMS

Trong Java Platform Module System (JPMS), `static` và `transitive` là hai modifier của chỉ thị `requires`. Chúng giải quyết hai vấn đề khác nhau: `static` xác định dependency có bắt buộc ở runtime hay không; `transitive` xác định khả năng đọc module có được truyền tiếp cho các module phụ thuộc hay không. Khi một dependency chỉ cần ở thời điểm biên dịch nhưng vẫn phải được nhìn thấy bởi người dùng API của module, có thể kết hợp chúng thành `requires static transitive`.

## 1. Vị trí của `requires` trong module descriptor

Mỗi named module khai báo các module mà nó phụ thuộc trong `module-info.java`. Một chỉ thị cơ bản có dạng:

```java
module com.acme.catalog {
    requires com.acme.money;
}
```

`requires com.acme.money` tạo dependency trực tiếp từ `com.acme.catalog` tới `com.acme.money`. Module phụ thuộc phải có thể được tìm thấy khi biên dịch và phải được phân giải trong môi trường runtime của ứng dụng sử dụng module đó. Chỉ thị `requires` không tự đóng gói mã của dependency vào JAR; việc phân phối artifact vẫn do hệ thống build và cách triển khai ứng dụng quyết định.

Trong JPMS, cần phân biệt ba khái niệm:

- **Dependency:** module này cần module khác để biên dịch hoặc chạy.
- **Readability:** module này có quyền đọc các kiểu công khai trong những package được module khác export.
- **Resolution:** JVM xác định tập module được đưa vào module layer khi khởi chạy.

`static` điều chỉnh tính bắt buộc của dependency ở hai giai đoạn biên dịch/runtime. `transitive` điều chỉnh readability cho các module phụ thuộc tiếp theo. Hai modifier này không thay thế nhau.

## 2. Ý nghĩa của `transitive`

Khi module `A` khai báo `requires transitive B`, mọi module đọc được `A` cũng được phép đọc `B`. Đây là cách module `A` công bố rằng dependency `B` là một phần của hợp đồng API mà người dùng `A` cần truy cập.

Ví dụ, API của thư viện catalog trả về kiểu `Money` do module `com.acme.money` cung cấp:

```java
module com.acme.catalog.api {
    requires transitive com.acme.money;
    exports com.acme.catalog.api;
}
```

```java
package com.acme.catalog.api;

import com.acme.money.Money;

public interface ProductPrice {
    Money price();
}
```

Ứng dụng chỉ cần khai báo `requires com.acme.catalog.api;` vẫn có readability tới `com.acme.money`, nên có thể sử dụng kiểu `Money` xuất hiện trong API mà không phải khai báo thêm một dependency trực tiếp chỉ để đọc kiểu đó. Module `com.acme.money` vẫn phải export package chứa `Money`; `transitive` không tự export package và không mở các package nội bộ.

Đồ thị readability có thể hình dung như sau:

```text
com.acme.app
    | requires
    v
com.acme.catalog.api
    | requires transitive
    v
com.acme.money
```

`transitive` phù hợp khi kiểu hoặc hợp đồng của dependency xuất hiện trong API công khai và người dùng module cần đọc dependency đó. Nó không phải lựa chọn mặc định cho mọi dependency triển khai.

## 3. Ý nghĩa của `static`

Khi module khai báo `requires static B`, module `B` là dependency bắt buộc trong quá trình biên dịch nhưng không bắt buộc phải có khi phân giải module ở runtime.

Ví dụ:

```java
module com.acme.catalog {
    requires static com.acme.annotations;
    exports com.acme.catalog.api;
}
```

Compiler vẫn phải tìm được `com.acme.annotations` trên module path lúc biên dịch để xác minh các kiểu và annotation được sử dụng. Khi chạy ứng dụng, module này có thể vắng mặt nếu chức năng runtime không cần nạp hoặc gọi các lớp của nó.

`static` không có nghĩa là dependency được bỏ qua khi biên dịch. Nó cũng không tự làm dependency thành tùy chọn trong Maven hoặc Gradle; cấu hình dependency của build tool và module descriptor là hai lớp cấu hình riêng.

### Điều kiện để có thể bỏ dependency ở runtime

Việc module resolver cho phép thiếu dependency không bảo đảm mọi chương trình đều chạy được khi thiếu nó. Nếu bytecode thực tế cần nạp một lớp từ module đó, gọi phương thức của nó, tạo đối tượng của nó hoặc dùng kiểu đó trong đường thực thi runtime, ứng dụng có thể gặp lỗi liên kết hoặc nạp lớp, chẳng hạn `NoClassDefFoundError`.

Vì vậy, `requires static` thích hợp nhất với dependency có thể bỏ ở runtime, ví dụ annotation chỉ dùng trong source với `RetentionPolicy.SOURCE`, công cụ hoặc hợp đồng chỉ phục vụ biên dịch. Nếu dependency cung cấp kiểu runtime thiết yếu cho API, ứng dụng vẫn phải phân phối dependency đó hoặc module nên khai báo dependency runtime bắt buộc.

## 4. Kết hợp `static` và `transitive`

Cú pháp thường dùng là:

```java
requires static transitive com.acme.annotations;
```

Chỉ thị này kết hợp hai hiệu ứng:

1. **`static`:** dependency phải có khi biên dịch module, nhưng có thể không có khi phân giải ứng dụng ở runtime.
2. **`transitive`:** module khác phụ thuộc vào module hiện tại cũng có readability tới dependency này.

Do đó, `requires static transitive B` phù hợp khi module cần một dependency để biên dịch và muốn người dùng API của mình cũng đọc được dependency đó, trong khi dependency có thể vắng mặt ở runtime. Một trường hợp phù hợp là annotation compile-time có retention `SOURCE`, được dùng trong API hoặc trong mã nguồn của người dùng API nhưng không cần tồn tại trong bytecode runtime.

Không dùng kết hợp này chỉ vì muốn giảm số dòng `requires`. Nếu kiểu của `B` là một phần của API runtime, hoặc code của module cần `B` khi chạy, hãy cân nhắc `requires transitive B` để thể hiện đúng dependency bắt buộc.

## 5. So sánh các lựa chọn

| Chỉ thị | Bắt buộc khi biên dịch | Bắt buộc khi runtime | Readability truyền tiếp | Trường hợp điển hình |
|---|---:|---:|---:|---|
| `requires B` | Có | Có | Không | Dependency trực tiếp, chỉ module hiện tại cần đọc. |
| `requires transitive B` | Có | Có | Có | Dependency runtime xuất hiện trong API công khai. |
| `requires static B` | Có | Không | Không | Dependency compile-time tùy chọn đối với người dùng module. |
| `requires static transitive B` | Có | Không | Có | Dependency compile-time cần được truyền readability, nhưng không cần ở runtime. |

Chọn theo hai câu hỏi độc lập: dependency có cần ở runtime không, và người dùng module có cần readability tới dependency không? Trả lời hai câu hỏi này trước khi chọn modifier.

## 6. Ví dụ hoàn chỉnh: annotation compile-time được truyền tiếp

Ví dụ dưới đây có ba module:

- `com.acme.annotations` cung cấp annotation `CompileTimeMarker` với `RetentionPolicy.SOURCE`.
- `com.acme.api` dùng annotation và khai báo `requires static transitive com.acme.annotations`.
- `com.acme.app` chỉ `requires com.acme.api`, nhưng vẫn có thể import và dùng annotation nhờ readability được truyền tiếp.

Cấu trúc source:

```text
workspace/
└── src/
    ├── com.acme.annotations/
    │   ├── module-info.java
    │   └── com/acme/annotations/CompileTimeMarker.java
    ├── com.acme.api/
    │   ├── module-info.java
    │   └── com/acme/api/Api.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
```

**Module annotation — `src/com.acme.annotations/module-info.java`:**

```java
module com.acme.annotations {
    exports com.acme.annotations;
}
```

**Annotation — `src/com.acme.annotations/com/acme/annotations/CompileTimeMarker.java`:**

```java
package com.acme.annotations;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
public @interface CompileTimeMarker {
}
```

`RetentionPolicy.SOURCE` có nghĩa annotation được compiler sử dụng từ source nhưng không được lưu trong file class. Đây là lý do cụ thể khiến ví dụ có thể bỏ module annotation ở runtime.

**Module API — `src/com.acme.api/module-info.java`:**

```java
module com.acme.api {
    requires static transitive com.acme.annotations;
    exports com.acme.api;
}
```

**Lớp API — `src/com.acme.api/com/acme/api/Api.java`:**

```java
package com.acme.api;

import com.acme.annotations.CompileTimeMarker;

public final class Api {
    @CompileTimeMarker
    public String message() {
        return "static + transitive";
    }
}
```

**Module ứng dụng — `src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.api;
}
```

**Lớp chạy — `src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import com.acme.api.Api;
import com.acme.annotations.CompileTimeMarker;

public class Main {
    @CompileTimeMarker
    public static void main(String[] args) {
        System.out.println(new Api().message());
    }
}
```

### Biên dịch và chạy

Thực hiện từ thư mục `workspace/` bằng JDK 17 trở lên:

```shell
javac --module-source-path src -d out -m com.acme.annotations,com.acme.api,com.acme.app
```

Lệnh biên dịch đưa cả ba module lên module source path. `com.acme.app` không khai báo `requires com.acme.annotations`; nó đọc được annotation vì module API đã khai báo dependency `static transitive`.

Để kiểm tra dependency có thể vắng mặt ở runtime, tạo thư mục runtime chỉ chứa hai module API và app, không copy `com.acme.annotations`:

```shell
mkdir runtime
cp -R out/com.acme.api out/com.acme.app runtime/
java --module-path runtime -m com.acme.app/com.acme.app.Main
```

Kết quả stdout:

```text
static + transitive
```

Ví dụ đã được biên dịch bằng JDK 24 và chạy với module path chỉ chứa `com.acme.api` và `com.acme.app`; module annotation đã được bỏ khỏi runtime image. Kết quả xác nhận annotation source-retention có thể được truyền readability ở compile time nhưng không cần hiện diện ở runtime.

## 7. Khi nào không nên dùng `static transitive`

- **Dependency runtime bắt buộc:** nếu API trả về hoặc nhận tham số là kiểu cần có ở runtime, không nên khai báo static chỉ để cho phép thiếu JAR. Dùng `requires transitive` nếu người dùng API cũng cần đọc module đó.
- **Dependency chỉ phục vụ nội bộ:** nếu người dùng module không cần đọc dependency, không thêm `transitive`. Dùng `requires` hoặc `requires static` tùy yêu cầu runtime.
- **Dependency chỉ là implementation detail:** tránh để dependency nội bộ rò rỉ vào hợp đồng module. Giữ package triển khai không export và chỉ khai báo readability cần thiết.
- **Dependency không có trên module path khi biên dịch:** `requires static` vẫn cần compiler quan sát được module; thêm dependency compile-time phù hợp vào module path.
- **Muốn dependency tự được đóng gói:** `requires transitive` và `requires static transitive` không copy JAR hoặc module vào artifact. Cần cấu hình packaging/runtime image riêng.

## 8. Lỗi thường gặp và cách xử lý

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `static` nghĩa là không cần dependency lúc biên dịch. | `javac` không phân giải được module hoặc annotation. | Đưa module lên module path khi biên dịch. |
| Dùng `transitive` cho mọi dependency. | Readability bị lan rộng, làm API module phụ thuộc vào chi tiết triển khai. | Chỉ truyền tiếp dependency mà người dùng API thực sự cần đọc. |
| Dùng `static` cho dependency runtime thiết yếu. | Có thể gặp lỗi nạp lớp hoặc liên kết khi chạy nếu dependency bị thiếu. | Dùng dependency runtime bắt buộc và đóng gói nó. |
| Cho rằng `transitive` tự export mọi package. | Consumer vẫn không đọc được package chưa export. | Export đúng package trong module descriptor của dependency. |
| Cho rằng `static transitive` tự tải dependency lúc chạy. | Ứng dụng thiếu module khi code cần dùng nó. | Phân phối module ở runtime khi đường thực thi cần module đó. |
| Nhầm JPMS với dependency scope của Maven/Gradle. | Cấu hình build và module graph không nhất quán. | Kiểm tra cả dependency của build tool và `module-info.java`. |

## 9. Checklist lựa chọn

- Xác định dependency có được sử dụng trong source/API và có cần thiết khi chạy hay không.
- Nếu dependency bắt buộc ở runtime, dùng `requires` hoặc `requires transitive`.
- Nếu dependency chỉ cần khi biên dịch và có thể vắng mặt ở runtime, cân nhắc `requires static`.
- Chỉ thêm `transitive` nếu consumer của module hiện tại cần readability tới dependency.
- Dùng `requires static transitive` khi cả hai điều kiện cùng đúng; ví dụ điển hình là annotation compile-time được consumer dùng trực tiếp.
- Nếu dependency xuất hiện trong API runtime, bảo đảm nó có mặt trong runtime image dù descriptor dùng static hay không.
- Kiểm tra compile bằng module path và chạy thử với đúng tập module dự kiến triển khai.

## Tài liệu tham khảo

- [Java Language Specification — Module Declarations and Dependencies (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.1)
- [Java Platform Module System — Module Resolution (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ModuleLayer.html)
- [The `javac` Command — Module Source Path (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
