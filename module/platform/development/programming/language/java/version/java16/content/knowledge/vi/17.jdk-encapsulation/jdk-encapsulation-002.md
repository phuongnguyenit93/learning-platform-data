# Phân biệt API công khai, package exported và JDK internal

> **Học phần:** `JAVA_VERSION_JAVA16` · **Chương:** Đóng gói JDK. Hệ module của Java kiểm soát package nào có thể được module khác sử dụng và package nào chỉ mở cho reflection ở runtime. Vì vậy, một class có modifier `public` chưa chắc đã là API mà ứng dụng khác có thể truy cập; một package được `exports` cũng chưa chắc là API chuẩn Java SE hoặc có cam kết tương thích lâu dài. Bài học phân biệt API công khai được tài liệu hóa, package được module export, package được open cho deep reflection và các JDK internal API; đồng thời hướng dẫn kiểm tra dependency và xử lý lỗi truy cập trong Java hiện đại.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt modifier truy cập Java với ranh giới truy cập giữa các module.
- Giải thích package được export trong `module-info.java`.
- Phân biệt `exports` với `opens` và deep reflection.
- Nhận biết JDK internal API và hiểu vì sao không nên phụ thuộc vào chúng.
- Hiểu sự thay đổi strong encapsulation từ Java 16 sang Java 17 trở lên.
- Dùng `jdeps --jdk-internals` để phát hiện tham chiếu tĩnh tới JDK internals.
- Đọc và xử lý lỗi `IllegalAccessError` hoặc `InaccessibleObjectException`.
- Dùng `--add-exports` và `--add-opens` như giải pháp chuyển tiếp có phạm vi hẹp khi thật sự cần.

## 1. Ba khái niệm cần tách biệt

Khi nói một API là “public”, có ba câu hỏi khác nhau:

1. **Java access control:** class, method hoặc field có modifier `public`, `protected`, package-private hay `private`?
2. **Module access:** package chứa kiểu đó có được module export cho module đang gọi không?
3. **API support contract:** API có được tài liệu hóa và cam kết hỗ trợ tương thích cho ứng dụng hay chỉ là chi tiết triển khai nội bộ?

Một khai báo `public` chỉ trả lời câu hỏi thứ nhất. Với named module, package còn phải được export thì module khác mới có thể truy cập public type trong package theo quy tắc module system. Ngay cả khi package được export, điều đó không tự động biến mọi type trong package thành Java SE API có cam kết tương thích như các API được đặc tả.

### 1.1. Public trong Java không đồng nghĩa public giữa các module

Ví dụ module ứng dụng:

```java
module com.example.billing {
    exports com.example.billing.api;
}
```

Một class công khai trong package đã export:

```java
package com.example.billing.api;

public record InvoiceView(String invoiceNumber, long totalCents) {}
```

Một class cũng có modifier `public` nhưng nằm trong package chưa export:

```java
package com.example.billing.internal;

public final class InvoiceEngine {
    public void recalculate() {
        // Implementation detail.
    }
}
```

Module khác có thể dùng `InvoiceView` thông qua package `com.example.billing.api`, nhưng không thể import `InvoiceEngine` từ named module `com.example.billing` chỉ vì class đó là `public`. Package `com.example.billing.internal` không được export nên bị module boundary che lại.

Đây là điểm cốt lõi của module encapsulation: modifier Java điều khiển khả năng truy cập ở cấp class/member; module descriptor quyết định package nào được đưa ra khỏi module.

### 1.2. Module consumer phải đọc module cung cấp API

Một module consumer thường khai báo dependency bằng `requires`:

```java
module com.example.web {
    requires com.example.billing;
}
```

Sau đó consumer có thể import kiểu trong package đã export:

```java
package com.example.web;

import com.example.billing.api.InvoiceView;

public final class InvoiceController {
    public InvoiceView view() {
        return new InvoiceView("INV-100", 125_000);
    }
}
```

Để truy cập thành công, module cần được resolve trong module graph, consumer cần đọc module cung cấp API và package cần được export cho consumer. `requires` không tự export package của module được yêu cầu; `exports` và `requires` phục vụ hai hướng khác nhau.

## 2. API công khai là một hợp đồng được hỗ trợ

Một API công khai dành cho ứng dụng thường có những đặc điểm:

- Có tài liệu API chính thức hoặc tài liệu của thư viện.
- Được thiết kế để lập trình viên bên ngoài sử dụng.
- Có quy tắc tương thích và chính sách thay đổi được công bố.
- Không yêu cầu truy cập vào implementation detail hoặc cấu trúc private của runtime.
- Có thể được dùng qua dependency và package boundary được công bố.

Với Java platform, API Java SE được định nghĩa trong đặc tả Java và tài liệu API tương ứng. JDK cũng có một số API được tài liệu hóa nhưng thuộc module mở rộng của JDK, không phải toàn bộ đều nằm trong Java SE specification. Vì vậy, khi chọn dependency, cần hiểu phạm vi hỗ trợ và mức độ portable của API.

Ví dụ `java.time`, `java.nio`, `java.util` và `java.lang.invoke` là các package API công khai được tài liệu hóa. Ứng dụng có thể dùng chúng qua module tương ứng mà không phải truy cập `jdk.internal.*`.

### 2.1. Exported package không tự động là Java SE API

Giả sử một module thư viện có:

```java
module com.example.analytics {
    exports com.example.analytics.api;
}
```

Package `com.example.analytics.api` được export, nên module consumer có thể truy cập public type trong package đó nếu có dependency phù hợp. Tuy nhiên, đây là API của thư viện `com.example.analytics`, không phải API Java SE. Mức độ tương thích do thư viện đó quy định.

Tương tự, một package JDK được export có thể là API JDK-specific được tài liệu hóa, nhưng không nhất thiết thuộc Java SE. Không nên đánh đồng “exported” với “được chuẩn hóa trong Java SE”.

### 2.2. Public type trong package không export vẫn bị module boundary chặn

| Java declaration | Package exported? | Named module khác truy cập trực tiếp? |
|---|---:|---|
| `public class ApiType` | Có | Có, nếu module graph cho phép |
| `public class InternalType` | Không | Không |
| package-private class | Có | Không truy cập trực tiếp từ package khác |
| `private` member | Có | Không truy cập trực tiếp bằng Java source |
| `public` member trong non-exported package | Không | Không qua module boundary thông thường |

`exports` không biến mọi member thành public. Nó chỉ cho phép module khác truy cập những type và member vốn đã được Java access control cho phép.

## 3. Exports: công bố package cho module khác

Trong `module-info.java`, directive `exports` công bố một package:

```java
module com.example.orders {
    exports com.example.orders.api;
}
```

Package `com.example.orders.api` trở thành package được export không điều kiện. Các module đọc `com.example.orders` có thể truy cập public type và các member được phép trong package đó.

Một module có thể export nhiều package:

```java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.events;
}
```

Chỉ export những package thực sự là hợp đồng sử dụng bên ngoài. Giữ package implementation như `internal`, `bootstrap` hoặc `persistence` ở trạng thái không export giúp giảm bề mặt API và cho phép thay đổi implementation mà ít ảnh hưởng consumer hơn.

### 3.1. Qualified exports

Nếu package chỉ cần công bố cho một số module cụ thể, dùng qualified export:

```java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.spi to com.example.integration;
}
```

Trong ví dụ:

- Mọi module đọc `com.example.orders` đều có thể dùng package `com.example.orders.api`.
- Chỉ module `com.example.integration` được phép truy cập public type trong `com.example.orders.spi`.
- Module khác không được truy cập `spi` qua module boundary.

Qualified exports hữu ích cho SPI hoặc package tích hợp nội bộ giữa một nhóm module. Nó giúp tránh công bố package cho toàn bộ module graph.

### 3.2. Export không phải deep reflection

`exports` cho phép truy cập các public type và member được Java access control cho phép. Nó không mở toàn bộ private member để framework dùng reflection.

Ví dụ, nếu framework cần đọc private field hoặc gọi private constructor, package có thể cần được `opens` cho module framework. Chỉ thêm `exports` thường không giải quyết được lỗi deep reflection.

## 4. Opens: cho phép reflection ở runtime

Directive `opens` cho phép module khác truy cập reflective sâu vào các type và member trong package ở runtime. Nó thường được dùng khi framework cần:

- Đọc private field để ánh xạ object.
- Gọi constructor không public.
- Truy cập member bằng `setAccessible` hoặc `trySetAccessible`.
- Thực hiện serialization/deserialization dựa trên reflection.
- Tạo proxy hoặc inject dependency bằng reflection.

Ví dụ:

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence to com.example.mapper;
}
```

Module `com.example.mapper` có thể dùng deep reflection vào package `com.example.orders.persistence` ở runtime. Package này vẫn không trở thành package có thể import trực tiếp từ Java source của module khác.

### 4.1. Phân biệt exports và opens

| Directive | Truy cập source/compile-time | Reflection public member | Deep reflection private member |
|---|---:|---:|---:|
| `exports p` | Có, theo Java access control | Có | Không mặc định |
| `opens p` | Không | Có ở runtime | Có ở runtime |
| `exports p to m` | Có với module `m` | Có với `m` | Không mặc định |
| `opens p to m` | Không | Có ở runtime với `m` | Có ở runtime với `m` |

`opens` không thay thế `exports`. Nếu consumer cần import public type trong package, package vẫn phải được export. Nếu chỉ framework cần reflection, có thể mở package cho đúng module framework mà không công bố nó như API source-level.

### 4.2. Qualified opens

Giới hạn quyền mở cho đúng module framework:

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence to com.example.orm;
    opens com.example.orders.serialization to com.example.json;
}
```

Cách này tốt hơn việc mở mọi package cho mọi module. Tên module đích phải khớp module name thực tế của framework đang chạy trên module path.

### 4.3. Open module

Có thể khai báo:

```java
open module com.example.legacyintegration {
    requires com.example.framework;
}
```

Một open module mở tất cả package của nó cho deep reflection ở runtime. Điều đó không đồng nghĩa tất cả package được export để module khác import ở compile-time. `open module` cũng không cần khai báo từng `opens` directive; nếu chỉ một vài package cần reflection, qualified `opens` thường thể hiện quyền hẹp hơn.

## 5. Kiểm tra deep reflection bằng trySetAccessible

Ví dụ module có package persistence được mở cho module mapper:

```java
module com.example.orders {
    opens com.example.orders.persistence to com.example.mapper;
}
```

Một class trong module `com.example.mapper` có thể thử bật quyền truy cập reflective:

```java
import java.lang.reflect.Field;

Field field = OrderEntity.class.getDeclaredField("status");

if (!field.trySetAccessible()) {
    throw new IllegalStateException(
            "Package is not open to this module");
}

Object value = field.get(entity);
```

`trySetAccessible()` trả về `false` nếu quyền truy cập không thể được bật theo quy tắc module/access control. Phương thức `setAccessible(true)` có thể ném `InaccessibleObjectException` khi không thể mở quyền truy cập.

Không nên dùng reflection để xuyên qua encapsulation nếu API công khai hoặc phương thức nghiệp vụ có thể đáp ứng nhu cầu. Deep reflection tạo thêm phụ thuộc vào cấu trúc nội bộ, dễ bị ảnh hưởng khi thư viện thay đổi implementation.

## 6. JDK internal API là gì?

JDK internal API là các class, package hoặc member phục vụ implementation của JDK, không được thiết kế như hợp đồng ổn định cho ứng dụng bên ngoài. Các package có tên như `jdk.internal.*` hoặc nhiều package `sun.*` thường là dấu hiệu cần kiểm tra kỹ.

Ví dụ về các loại phụ thuộc không nên đưa vào ứng dụng mới:

- Dùng `jdk.internal.*` để gọi implementation nội bộ của JDK.
- Dùng class trong `sun.*` thay cho API Java được tài liệu hóa.
- Dùng reflection để truy cập private field của class trong `java.base`.
- Dựa vào layout, field hoặc method nội bộ của JDK để tối ưu.
- Dùng classloader hoặc compiler implementation detail không có hợp đồng hỗ trợ.

Không thể kết luận chỉ từ prefix package. Một số package bắt đầu bằng `com.sun.*` là API JDK được tài liệu hóa và được export; một số API như vậy vẫn là JDK-specific, không thuộc Java SE. Ngược lại, có internal API đặc biệt vẫn được export vì lý do tương thích nhưng không vì thế trở thành API được hỗ trợ ổn định. Hãy kiểm tra tài liệu API và module descriptor thay vì chỉ nhìn tên package.

Một ví dụ đáng chú ý là `sun.misc.Unsafe`. API này vẫn được giữ và export trong module `jdk.unsupported` vì lý do tương thích với một số thư viện, nhưng điều đó không biến nó thành Java SE API hay một lựa chọn mặc định cho ứng dụng mới. Nếu nhu cầu là thao tác nguyên tử trên field, hãy xem `VarHandle`; nếu cần thao tác byte, hãy xem `ByteBuffer`. Các API thay thế chỉ phù hợp khi semantics của chúng đáp ứng đúng yêu cầu, không phải mọi thao tác mức thấp đều có phép thay thế một-một.

### 6.1. Vì sao phụ thuộc JDK internals nguy hiểm?

JDK có thể thay đổi hoặc loại bỏ implementation detail giữa các phiên bản. Ứng dụng phụ thuộc vào internal API có thể:

- Không biên dịch được khi nâng JDK.
- Ném `IllegalAccessError` khi module không export package.
- Ném `InaccessibleObjectException` khi reflection sâu bị chặn.
- Chạy khác nhau giữa vendor hoặc bản cập nhật JDK.
- Bị ảnh hưởng bởi thay đổi cấu trúc field/method nội bộ dù hành vi API công khai không đổi.

Một internal API có thể tồn tại nhiều năm nhưng điều đó không tạo ra cam kết tương thích. Sự tồn tại trong runtime không đồng nghĩa được hỗ trợ cho ứng dụng.

## 7. Strong encapsulation từ Java 16 đến Java hiện đại

Java Platform Module System được giới thiệu trong Java 9. Quá trình chuyển đổi ban đầu có giai đoạn tương thích để thư viện cũ có thời gian chuyển khỏi JDK internals.

Java 16 áp dụng strong encapsulation mặc định cho phần lớn internal API của JDK. Java 17 tiếp tục hoàn tất quá trình này qua JEP 403: các cơ chế truy cập rộng kiểu cũ không còn là giải pháp để mở toàn bộ JDK internals. Một số API nội bộ đặc biệt vẫn có thể được export vì lý do tương thích, nhưng vẫn không nên xem chúng là API ổn định.

Với Java hiện đại:

- Không thiết kế ứng dụng mới dựa trên JDK internal packages.
- Không dựa vào chế độ truy cập rộng lịch sử để chạy thư viện cũ.
- Cập nhật thư viện và thay thế internal API bằng API được tài liệu hóa.
- Chỉ dùng `--add-exports` hoặc `--add-opens` khi có lý do cụ thể, với đúng package và module đích.
- Ghi nhận và loại bỏ các override chuyển tiếp sau khi dependency đã được sửa.

Tùy chọn lịch sử `--illegal-access` không còn mở rộng quyền truy cập như giai đoạn chuyển tiếp ban đầu. Không dùng nó làm hướng dẫn migration hoặc cấu hình triển khai.

## 8. Dùng jdeps để tìm phụ thuộc JDK internal

JDK cung cấp công cụ `jdeps` để phân tích dependency trong class file và JAR. Tùy chọn `--jdk-internals` báo cáo các tham chiếu tĩnh tới JDK internal API mà công cụ nhận diện được.

Ví dụ:

```text
jdeps --jdk-internals application.jar
```

Có thể phân tích dependency đệ quy:

```text
jdeps --jdk-internals --recursive application.jar
```

Kết quả có thể cho biết class nào phụ thuộc vào internal API nào và gợi ý API thay thế khi có. Đọc báo cáo rồi truy ngược dependency để xác định tham chiếu đến từ code ứng dụng hay thư viện bên thứ ba.

### 8.1. Giới hạn của jdeps

`jdeps` phân tích dependency có thể nhìn thấy trong bytecode. Nó không thể phát hiện đầy đủ mọi truy cập được tạo động, ví dụ:

- `Class.forName()` nhận tên class từ file cấu hình.
- Reflection dùng tên package/class được ghép ở runtime.
- Bytecode được sinh trong lúc chạy.
- Native code truy cập runtime internals.

Vì vậy, `jdeps` là một bước kiểm tra hữu ích chứ không phải bằng chứng tuyệt đối rằng ứng dụng không còn phụ thuộc nội bộ. Kết hợp nó với test integration trên JDK mục tiêu, log runtime và kiểm tra dependency/framework.

### 8.2. Xem package được export trong module JDK

Có thể yêu cầu launcher mô tả module của JDK:

```text
java --describe-module java.base
```

Kết quả hiển thị tên module, các package được export và những directive liên quan. Đây là cách kiểm tra module descriptor của runtime đang dùng; output có thể khác giữa các phiên bản JDK. Không suy luận rằng một package được export là Java SE API: vẫn cần xem tài liệu và phạm vi hỗ trợ của API.

## 9. Xử lý lỗi truy cập module

Hai nhóm lỗi thường gặp:

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `IllegalAccessError` | Bytecode đã tham chiếu type/member nhưng module không cho truy cập ở runtime | Kiểm tra package export, module graph và dependency |
| `InaccessibleObjectException` | Reflection muốn mở sâu member nhưng package không được open phù hợp | Kiểm tra `opens`, module đích và cách framework reflection |

Trước khi thêm JVM flag, xác định package, module nguồn, module đích và thao tác thực sự cần quyền nào. Truy cập source-level tới public type và deep reflection là hai vấn đề khác nhau.

### 9.1. --add-exports: mở package cho truy cập kiểu công khai

Cú pháp tổng quát:

```text
--add-exports source.module/package=target.module
```

Ví dụ dạng cú pháp với package nội bộ của một module ứng dụng:

```text
--add-exports com.example.orders/com.example.orders.internal=com.example.migration
```

Flag này mở rộng export của package cho module đích, cho phép truy cập các public type/member vốn bị module boundary chặn. Nó không mở private field cho deep reflection.

Có thể dùng ở compile time với `javac` và runtime với `java`, nhưng cần cấu hình nhất quán. Với ứng dụng chạy trên classpath, target có thể là `ALL-UNNAMED`:

```text
--add-exports source.module/package=ALL-UNNAMED
```

### 9.2. --add-opens: cho phép deep reflection ở runtime

Cú pháp tổng quát:

```text
--add-opens source.module/package=target.module
```

Ví dụ:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

Flag này mở package cho deep reflection của module đích ở runtime. Nó không cho phép import các type trong package đó khi biên dịch Java source.

`--add-opens` thường là cấu hình chuyển tiếp cho framework hoặc thư viện cũ. Chỉ mở package cần thiết, chỉ cho đúng module đích và có kế hoạch loại bỏ sau khi nâng cấp dependency. Tránh mở toàn bộ module cho `ALL-UNNAMED` nếu không cần.

### 9.3. Không nhầm hai flag

| Nhu cầu | Cơ chế |
|---|---|
| Module khác cần import public type trong package chưa export | `exports` hoặc `--add-exports` |
| Một module cụ thể cần import package | Qualified `exports ... to ...` |
| Framework cần reflection sâu vào private member | `opens` hoặc `--add-opens` |
| Chỉ cần gọi public API được hỗ trợ | Dùng API đó; không thêm flag |
| Code dùng JDK internal API | Tìm API thay thế và nâng cấp dependency |

Các flag không biến JDK internal API thành API được hỗ trợ. Chúng chỉ thay đổi quyền truy cập trong một lần chạy/biên dịch cụ thể; chúng không tạo cam kết rằng API nội bộ sẽ còn tồn tại ở JDK tiếp theo.

## 10. Quy trình migration khỏi JDK internals

Khi nâng ứng dụng lên JDK mới và gặp lỗi encapsulation, thực hiện theo trình tự:

1. **Xác định caller:** lỗi đến từ code ứng dụng hay dependency bên thứ ba?
2. **Xác định module/package:** đọc thông báo lỗi để biết module nguồn, package và module đích.
3. **Kiểm tra API thay thế:** tìm API Java SE hoặc API JDK được tài liệu hóa phù hợp.
4. **Nâng cấp dependency:** dùng phiên bản thư viện đã hỗ trợ strong encapsulation.
5. **Chỉnh module descriptor:** export package API của chính ứng dụng hoặc open package hẹp cho framework nếu thực sự cần.
6. **Dùng flag chuyển tiếp có giới hạn:** chỉ khi chưa thể sửa dependency ngay và đã hiểu quyền cần cấp.
7. **Chạy `jdeps --jdk-internals`:** kiểm tra lại tham chiếu tĩnh.
8. **Test trên JDK mục tiêu:** chạy unit, integration và packaging test trong cùng môi trường triển khai.
9. **Gỡ flag chuyển tiếp:** xác minh ứng dụng vẫn hoạt động sau khi bỏ `--add-exports`/`--add-opens` không còn cần thiết.

Không giải quyết mọi lỗi bằng cách mở rộng quyền toàn cục. Cách đó che khuất dependency chưa được cập nhật và khiến module boundary mất tác dụng.

## 11. Ví dụ module hoàn chỉnh

Một module có API công khai, SPI chỉ dành cho integration module và package persistence chỉ mở cho mapper:

```java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.spi to com.example.integration;

    opens com.example.orders.persistence to com.example.mapper;
}
```

Cấu trúc package:

```text
com.example.orders
  +-- api
  |     +-- OrderView.java
  |     +-- OrderService.java
  |
  +-- spi
  |     +-- OrderPlugin.java
  |
  +-- persistence
  |     +-- OrderEntity.java
  |
  +-- internal
        +-- OrderEngine.java
```

| Package | Quyền | Mục đích |
|---|---|---|
| `api` | Export không điều kiện | Hợp đồng cho consumer |
| `spi` | Qualified export | Chỉ integration module dùng |
| `persistence` | Open cho mapper | Deep reflection ở runtime |
| `internal` | Không export, không open | Implementation detail |

Cách thiết kế này giảm bề mặt public API và chỉ cấp quyền reflection cho nơi cần thiết. Nếu framework không cần reflection vào persistence package, bỏ `opens` để giữ encapsulation chặt hơn.

## 12. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế | Cách hiểu đúng |
|---|---|---|
| Class `public` thì module khác luôn truy cập được | Package có thể chưa export | Kiểm tra cả access modifier và module descriptor |
| Package exported là Java SE API | Export chỉ nói về module visibility | Kiểm tra tài liệu và cam kết API |
| `exports` cho phép framework đọc private field | Export không mở deep reflection | Dùng `opens` nếu framework thật sự cần |
| `opens` cho phép import package ở compile time | Opens chỉ cấp reflective access ở runtime | Dùng exports cho source-level access |
| Mọi package `com.sun.*` đều là internal | Có package JDK-specific được tài liệu hóa | Kiểm tra từng API/module |
| Internal API vẫn dùng được nghĩa là được hỗ trợ | Có API nội bộ còn hiện diện vì tương thích | Tránh phụ thuộc và thay bằng API được tài liệu hóa |
| `--add-opens` làm API ổn định hơn | Flag chỉ mở quyền reflection ở runtime | Coi là ngoại lệ chuyển tiếp |
| `--add-exports` và `--add-opens` giống nhau | Một cái mở truy cập public type; một cái mở deep reflection | Chọn theo thao tác cần thực hiện |
| `jdeps` tìm được mọi reflection | Truy cập động có thể không xuất hiện trong bytecode dependency graph | Kết hợp kiểm tra runtime và integration test |
| `--illegal-access` là giải pháp hiện đại | Cơ chế mở rộng lịch sử không còn tác dụng như trước | Dùng API thay thế hoặc quyền hẹp khi cần |

## 13. Checklist trước khi công bố API module

Trước khi phát hành một module thư viện:

1. Package nào là API dành cho consumer?
2. Package nào chỉ là implementation detail?
3. Public type có tài liệu và cam kết tương thích rõ ràng không?
4. Có cần qualified exports cho SPI không?
5. Framework có thực sự cần deep reflection không?
6. Có thể dùng constructor/accessor hoặc API công khai thay reflection không?
7. Có package nào đang bị mở rộng quá rộng không?
8. `jdeps --jdk-internals` có báo cáo dependency nội bộ không?
9. Đã kiểm tra cả dependency bên thứ ba và code tự viết chưa?
10. Đã test trên JDK mục tiêu mà không dựa vào cơ chế truy cập lịch sử chưa?
11. Có kế hoạch bỏ các `--add-exports` hoặc `--add-opens` chuyển tiếp không?

## 14. Bài tập vận dụng

**Bài 1 — Export:** Tạo module `com.example.billing` với package `api` và `internal`. Export package `api`, tạo public class trong cả hai package và thử import từ module consumer. Giải thích vì sao chỉ một class truy cập được.

**Bài 2 — Qualified export:** Export package `spi` chỉ cho module `com.example.integration`. Thử import từ module thứ ba và quan sát lỗi module access.

**Bài 3 — Opens:** Tạo private field trong entity và thử `trySetAccessible()` từ module mapper. Thêm qualified `opens` rồi so sánh kết quả. Kiểm tra `opens` không làm package importable ở compile time.

**Bài 4 — Phân tích JDK internals:** Chạy `jdeps --jdk-internals` trên một JAR có dependency cũ. Xác định class và internal package được tham chiếu; tìm API thay thế hoặc phiên bản thư viện đã sửa.

**Bài 5 — Migration:** Tạo một cấu hình test dùng `--add-opens` cho package cần reflection. Sau đó nâng dependency hoặc thay cách truy cập để bỏ flag và xác minh integration test vẫn chạy.

---

## Tài liệu tham khảo

- [JEP 261 — Module System](https://openjdk.org/jeps/261): module graph, exports, opens và ranh giới truy cập.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): thay đổi strong encapsulation mặc định trong Java 16.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation trong Java 17 và các bản Java hiện đại.
- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html): cú pháp và ngữ nghĩa `exports`, `opens`, `requires`.
- [Module — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): API module và các thao tác kiểm tra exports/opens.
- [jdeps — Java Dependency Analysis Tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): phân tích dependency và phát hiện tham chiếu JDK internal API.
- [java launcher — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): các tùy chọn `--add-exports` và `--add-opens`.

---

**Ghi nhớ:** `public` là quyền truy cập ở cấp Java; `exports` công bố package cho module khác; `opens` cấp deep reflection ở runtime; API được hỗ trợ còn cần tài liệu và cam kết tương thích. JDK internal API là implementation detail, kể cả khi một số package vẫn truy cập được. Hãy ưu tiên API được tài liệu hóa, dùng `jdeps` để tìm tham chiếu và chỉ mở quyền hẹp khi cần.
