# requires static trong Java Module System

Java Platform Module System (JPMS) cho phép một module khai báo module khác là dependency bằng directive `requires` trong `module-info.java`. Thông thường, dependency được yêu cầu phải có mặt cả khi biên dịch lẫn khi chạy. Tuy nhiên, có những thư viện chỉ cần thiết để compiler hiểu kiểu dữ liệu, annotation hoặc API mở rộng; ứng dụng vẫn cần chạy được khi thư viện đó không được cài đặt.

Directive `requires static` giải quyết trường hợp này: module phụ thuộc là bắt buộc trong giai đoạn biên dịch nhưng có thể vắng mặt trong module graph lúc chạy. Đây là cơ chế khai báo dependency tùy chọn của JPMS, không phải cơ chế tự động tải thư viện hoặc tự tạo fallback cho code.

## 1. Cú pháp và ý nghĩa

Khai báo trong `module-info.java`:

~~~java
module com.example.app {
    requires static com.example.metrics;
}
~~~

Module `com.example.app` cần module `com.example.metrics` để biên dịch. Khi chạy, `com.example.metrics` có thể không được phân giải vào runtime module graph.

Có thể hiểu theo hai giai đoạn:

| Giai đoạn | Hành vi của requires static |
|---|---|
| Biên dịch | Module được yêu cầu phải quan sát được và đọc được; compiler cần nó để phân giải kiểu và kiểm tra code |
| Chạy | Module không bắt buộc phải được phân giải; ứng dụng vẫn có thể khởi động nếu dependency vắng mặt |
| Khi dependency được phân giải bằng cách khác | Module yêu cầu có readability edge tới dependency và có thể sử dụng các kiểu của nó |
| Khi code thực sự cần kiểu nhưng dependency không được phân giải | Có thể phát sinh lỗi liên kết như `NoClassDefFoundError` |

`static` ở đây là modifier của directive `requires`. Nó không phải từ khóa `static` dùng để khai báo field, method hoặc nested class.

## 2. So sánh requires, requires transitive và requires static

Ba dạng thường gặp có mục đích khác nhau:

| Directive | Bắt buộc lúc biên dịch | Bắt buộc lúc chạy | Chuyển readability cho module phụ thuộc vào mình |
|---|---|---|---|
| `requires B;` | Có | Có | Không |
| `requires transitive B;` | Có | Có | Có |
| `requires static B;` | Có | Không | Không |
| `requires static transitive B;` | Có | Không | Có |

- `requires B` khai báo dependency thông thường. Nếu module B không có trong runtime module graph, quá trình phân giải module có thể thất bại.
- `requires transitive B` còn làm cho module đọc module hiện tại được đọc B theo quan hệ readability bắc cầu.
- `requires static B` giữ yêu cầu ở compile time và cho phép B vắng mặt ở runtime.
- `requires static transitive B` kết hợp hai modifier: B bắt buộc khi biên dịch, dependency được truyền cho module downstream ở compile time, nhưng vẫn tùy chọn khi chạy.

Không nên thêm `transitive` chỉ để làm dependency tùy chọn. Hãy dùng nó khi kiểu của module B xuất hiện trong API mà module khác cần biên dịch khi sử dụng API của module hiện tại.

## 3. Hai giai đoạn phân giải module

JPMS tạo module graph từ các module gốc (root modules) và các directive `requires` của chúng. Mỗi cạnh readability cho biết một module có thể đọc các kiểu được export từ module khác hay không.

### 3.1. Khi biên dịch

Với `requires static B`, module B phải có thể quan sát được trong môi trường biên dịch. Compiler cần đọc descriptor của B, biết package nào được export và phân giải các kiểu được tham chiếu trong source code.

Nếu B không có trên module path hoặc không export package mà code cần sử dụng, compiler sẽ báo lỗi. `static` không làm dependency trở thành tùy chọn ở compile time.

### 3.2. Khi chạy

Khi runtime phân giải module graph, directive `requires static` không tự yêu cầu runtime tìm module B. Vì vậy:

- B có thể không có trên module path mà ứng dụng vẫn khởi động.
- B có thể đang nằm trên module path nhưng vẫn không được đưa vào module graph chỉ vì `requires static` nhắc tới nó.
- B sẽ được phân giải nếu nó được kéo vào graph bằng một dependency bắt buộc khác hoặc được thêm tường minh bằng `--add-modules`.
- Khi B đã được phân giải theo một trong các cách đó, module có `requires static B` có thể đọc B.

Đây là điểm dễ nhầm nhất: **có tệp JAR trên module path không đồng nghĩa module đó đã được phân giải**.

## 4. Ví dụ hoàn chỉnh với dependency tùy chọn

Ta xây hai module:

- `com.example.app`: ứng dụng chính, có thể chạy ở chế độ cơ bản.
- `com.example.metrics`: thư viện mở rộng cung cấp thông tin metrics.

Khi module metrics được phân giải, ứng dụng gọi phần tích hợp. Khi nó chưa được phân giải, ứng dụng chạy ở chế độ cơ bản.

### 4.1. Cấu trúc thư mục

~~~text
project/
└── src/
    ├── com.example.app/
    │   ├── module-info.java
    │   └── com/example/app/
    │       ├── Main.java
    │       └── MetricsBridge.java
    └── com.example.metrics/
        ├── module-info.java
        └── com/example/metrics/
            └── Metrics.java
~~~

### 4.2. Khai báo module metrics

Tệp `src/com.example.metrics/module-info.java`:

~~~java
module com.example.metrics {
    exports com.example.metrics;
}
~~~

Tệp `src/com.example.metrics/com/example/metrics/Metrics.java`:

~~~java
package com.example.metrics;

public final class Metrics {
    private Metrics() {
    }

    public static String summary() {
        return "metrics enabled";
    }
}
~~~

Package `com.example.metrics` được export để module khác có thể dùng kiểu `Metrics`.

### 4.3. Khai báo module ứng dụng

Tệp `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires static com.example.metrics;
}
~~~

Module ứng dụng có thể biên dịch với API của metrics, nhưng không bắt buộc runtime phải phân giải module đó.

### 4.4. Tách phần tích hợp tùy chọn

Tệp `src/com.example.app/com/example/app/MetricsBridge.java`:

~~~java
package com.example.app;

import com.example.metrics.Metrics;

public final class MetricsBridge {
    private MetricsBridge() {
    }

    public static String summary() {
        return Metrics.summary();
    }
}
~~~

Class `MetricsBridge` tham chiếu trực tiếp đến module tùy chọn. Vì vậy, chỉ nên nạp class này khi module metrics thực sự có trong runtime graph.

### 4.5. Kiểm tra sự hiện diện trước khi nạp phần tích hợp

Tệp `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        boolean metricsResolved = ModuleLayer.boot()
                .findModule("com.example.metrics")
                .isPresent();

        if (!metricsResolved) {
            System.out.println("Optional metrics not resolved; core mode");
            return;
        }

        Class<?> bridge = Class.forName("com.example.app.MetricsBridge");
        String summary = (String) bridge.getMethod("summary").invoke(null);
        System.out.println("Optional metrics: " + summary);
    }
}
~~~

`Main` kiểm tra module graph bằng `ModuleLayer.boot().findModule(...)`. Nó chỉ nạp `MetricsBridge` qua reflection sau khi xác nhận module metrics đã được phân giải. Vì `Main` không có kiểu tham chiếu trực tiếp tới `Metrics` hoặc `MetricsBridge`, phần khởi động cơ bản không buộc JVM phải nạp class tích hợp tùy chọn.

### 4.6. Biên dịch hai module

Chạy từ thư mục `project`:

~~~bash
javac --module-source-path src -d mods -m com.example.metrics,com.example.app
~~~

Lệnh biên dịch cả hai module trong cùng một lượt. Module metrics phải có mặt trong source/module path ở giai đoạn này vì ứng dụng khai báo `requires static` và `MetricsBridge` sử dụng kiểu `Metrics`.

Sau khi biên dịch, cấu trúc đầu ra:

~~~text
mods/
├── com.example.app/
│   ├── module-info.class
│   └── com/example/app/
│       ├── Main.class
│       └── MetricsBridge.class
└── com.example.metrics/
    ├── module-info.class
    └── com/example/metrics/
        └── Metrics.class
~~~

### 4.7. Chạy mà không phân giải module tùy chọn

Chạy ứng dụng bình thường:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Dù module metrics đang nằm trên module path, nó không được phân giải chỉ vì directive `requires static` nhắc tới nó.

Stdout:

~~~text
Optional metrics not resolved; core mode
~~~

### 4.8. Chạy với module tùy chọn được phân giải

Thêm module metrics làm root module bằng `--add-modules`:

~~~bash
java --module-path mods --add-modules com.example.metrics -m com.example.app/com.example.app.Main
~~~

Khi đó metrics được đưa vào runtime module graph. Cạnh readability từ app tới metrics được thiết lập, `MetricsBridge` có thể được nạp và gọi.

Stdout:

~~~text
Optional metrics: metrics enabled
~~~

Ví dụ này minh họa cả hai trường hợp: dependency không được phân giải và dependency được phân giải theo yêu cầu tường minh.

## 5. Vì sao cần tách code sử dụng dependency tùy chọn?

`requires static` chỉ làm cho module dependency tùy chọn trong quá trình phân giải. Nó không tự bảo vệ những lệnh bytecode cần lớp từ dependency.

Nếu code gọi trực tiếp:

~~~java
Metrics.summary();
~~~

trong một đường chạy mà module metrics không được phân giải, JVM có thể không tìm thấy lớp khi cần liên kết hoặc thực thi và ném `NoClassDefFoundError`.

Các thực hành nên áp dụng:

1. Đưa code phụ thuộc trực tiếp vào module tùy chọn vào class riêng.
2. Tránh đặt kiểu tùy chọn trong chữ ký method, field hoặc constructor của lớp khởi động cơ bản nếu lớp đó phải hoạt động khi dependency vắng mặt.
3. Kiểm tra module có trong layer phù hợp trước khi nạp hoặc gọi phần tích hợp.
4. Chỉ dùng reflection hoặc cơ chế nạp động tại ranh giới tích hợp, không rải tên lớp dạng chuỗi khắp ứng dụng.
5. Xử lý trường hợp dependency không có bằng hành vi cơ bản rõ ràng.
6. Kiểm thử cả hai cấu hình: dependency được phân giải và không được phân giải.

Reflection không tự làm dependency trở nên an toàn. Nếu nạp class tham chiếu tới kiểu không có, thao tác nạp hoặc gọi vẫn có thể thất bại. Điều quan trọng là kiểm tra module graph trước khi nạp class tích hợp.

## 6. Khi nào nên dùng requires static?

Một số tình huống phù hợp:

### 6.1. Annotation chỉ cần khi biên dịch

Một thư viện annotation có thể chỉ phục vụ compiler, annotation processor hoặc công cụ build. Nếu ứng dụng không cần đọc annotation đó bằng reflection ở runtime, module annotation có thể được khai báo bằng `requires static`.

Cần xem `@Retention` của annotation và cách ứng dụng sử dụng nó. Nếu code runtime hoặc framework cần nạp annotation type để đọc metadata, module chứa annotation có thể vẫn phải được phân giải.

### 6.2. Tích hợp với thư viện tùy chọn

Ứng dụng có chức năng cơ bản nhưng có thể mở rộng khi cài thêm thư viện:

- Adapter cho một nhà cung cấp database cụ thể.
- Integration với thư viện metrics hoặc tracing.
- Bộ chuyển đổi định dạng chỉ có trong một gói mở rộng.
- API hỗ trợ nền tảng hoặc thiết bị chỉ có ở một số môi trường.

Trong các trường hợp này, phần tích hợp tùy chọn cần được tách biệt và chỉ nạp khi module đã sẵn sàng.

### 6.3. API có kiểu từ dependency tùy chọn

Một thư viện có thể cung cấp API mở rộng sử dụng kiểu của module tùy chọn. Khi module khác cần đọc các kiểu đó trong lúc biên dịch, có thể cần `requires static transitive`.

Hãy dùng dạng này khi dependency thực sự là một phần của API được truyền cho consumer. Nếu kiểu dependency chỉ được dùng nội bộ, `requires static` thường đủ và giữ quan hệ module gọn hơn.

## 7. Kết hợp static và transitive

Ví dụ:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
    exports com.example.api;
}
~~~

Ý nghĩa:

- Module `com.example.annotations` phải có mặt khi biên dịch module API.
- Module khác đọc `com.example.api` sẽ được truyền readability tới `com.example.annotations` trong giai đoạn biên dịch.
- Khi chạy, module annotations vẫn không bắt buộc phải được phân giải chỉ vì directive này.
- Nếu module annotations được phân giải bằng một dependency khác hoặc qua `--add-modules`, nó có thể tham gia runtime graph.

`transitive` không làm dependency tùy chọn trở thành bắt buộc ở runtime khi kết hợp với `static`. Hai modifier giải quyết hai khía cạnh riêng: truyền readability và thời điểm dependency bắt buộc.

## 8. requires static và dependency của Maven/Gradle

`requires static` nằm trong module descriptor. Nó không thay thế cấu hình dependency của công cụ build.

Ví dụ, Maven hoặc Gradle vẫn phải cung cấp artifact cần thiết trên module path trong quá trình compile. Việc artifact có được đóng gói vào runtime distribution hay không còn phụ thuộc cấu hình dependency, packaging và cách ứng dụng được triển khai.

Cần phân biệt:

| Thành phần | Trách nhiệm |
|---|---|
| `requires static` trong `module-info.java` | Khai báo quan hệ module: cần khi biên dịch, tùy chọn khi chạy |
| Maven/Gradle dependency configuration | Tải artifact, chọn phiên bản và đưa dependency vào compile/runtime classpath hoặc module path |
| `--module-path` | Cho compiler/launcher biết nơi tìm module |
| `--add-modules` | Yêu cầu launcher đưa module được chỉ định vào runtime graph |

Không nên chỉ sửa `module-info.java` mà quên cấu hình build. Nếu dependency không có trong compile module path, compiler không thể phân giải các kiểu được sử dụng.

## 9. Kiểm tra requires static trong module descriptor

Có thể xem descriptor của module đã biên dịch bằng:

~~~bash
javap -v mods/com.example.app/module-info.class
~~~

Trong phần `Module` attribute, tìm entry `requires` tương ứng với `com.example.metrics`. Flag `ACC_STATIC_PHASE` biểu thị dependency bắt buộc ở compile time và tùy chọn ở runtime. Nếu có thêm `transitive`, descriptor cũng có flag `ACC_TRANSITIVE`.

Có thể quan sát module graph lúc chạy bằng:

~~~bash
java --show-module-resolution --module-path mods -m com.example.app/com.example.app.Main
~~~

Sau đó thêm module rõ ràng:

~~~bash
java --show-module-resolution --module-path mods --add-modules com.example.metrics -m com.example.app/com.example.app.Main
~~~

So sánh hai lần chạy để thấy module metrics chỉ tham gia graph khi được kéo vào bằng một cách khác.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `module not found` khi biên dịch | Dependency không có trên compile module path hoặc không observable | Thêm module/JAR đúng vào module path của compiler |
| Ứng dụng vẫn báo thiếu module khi chạy | Dùng `requires` thông thường thay vì `requires static` | Kiểm tra directive trong `module-info.java` |
| Module có trên module path nhưng `findModule` trả về empty | `requires static` không tự phân giải module ở runtime | Dùng `--add-modules` hoặc một dependency runtime bắt buộc nếu thiết kế yêu cầu |
| `NoClassDefFoundError` khi gọi chức năng tùy chọn | Code đã nạp hoặc thực thi class tham chiếu dependency chưa được phân giải | Kiểm tra module graph trước khi nạp class tích hợp; cô lập code phụ thuộc |
| `IllegalAccessError` hoặc lỗi truy cập package | Module có mặt nhưng package cần thiết không được export hoặc không được đọc | Kiểm tra `exports`, readability và descriptor của module |
| Consumer không biên dịch được API của thư viện | Kiểu trong API đến từ dependency chưa được truyền readability | Cân nhắc `requires static transitive` nếu kiểu đó thực sự là phần của API |
| Build local chạy nhưng runtime distribution lỗi | Dependency chỉ có trong compile path, hoặc packaging khác dự kiến | Kiểm tra cấu hình Maven/Gradle và module path lúc triển khai |
| Nghĩ `requires static` tự cung cấp fallback | Nhầm optional resolution với xử lý lỗi trong code | Viết nhánh cơ bản và kiểm tra sự hiện diện của module |

## 11. Những giới hạn cần nhớ

- `requires static` không làm dependency trở nên tùy chọn ở compile time.
- Module có trên module path không nhất thiết đã được runtime phân giải.
- Khi module được phân giải bằng cách khác, module yêu cầu có thể đọc nó theo readability edge.
- Code vẫn có thể thất bại nếu thực sự tham chiếu tới class từ module vắng mặt.
- Directive không tải thư viện, không quản lý version và không cấu hình Maven/Gradle.
- `requires static` không đồng nghĩa với `requires transitive`; muốn truyền readability phải khai báo thêm `transitive`.
- `java.base` là module nền tảng được yêu cầu ngầm; không khai báo `requires static java.base`.
- Chỉ nên dùng dependency tùy chọn khi ứng dụng có hành vi rõ ràng cho trường hợp dependency không được phân giải.

## 12. Quy trình áp dụng

Khi muốn biến một dependency thành tùy chọn ở runtime:

1. **Xác định nhu cầu:** dependency có thực sự chỉ cần cho compile time hoặc một tính năng mở rộng không?
2. **Kiểm tra API:** code nào tham chiếu trực tiếp tới kiểu của dependency? Những class đó có thể được nạp độc lập với phần khởi động không?
3. **Khai báo module:** dùng `requires static module.name;`; chỉ thêm `transitive` khi consumer cần readability tới dependency.
4. **Cấu hình build:** bảo đảm dependency có mặt trên module path khi biên dịch.
5. **Tách phần tích hợp:** cô lập các class sử dụng dependency tùy chọn.
6. **Kiểm tra module graph:** dùng `ModuleLayer.findModule` hoặc `--show-module-resolution`.
7. **Chạy hai cấu hình:** thử khi dependency vắng mặt/không được phân giải và khi dependency được thêm bằng `--add-modules`.
8. **Kiểm thử lỗi liên kết:** xác nhận đường chạy cơ bản không nạp class tùy chọn khi module vắng mặt.
9. **Kiểm tra packaging:** xác nhận runtime image hoặc bộ cài chỉ chứa dependency theo chính sách phát hành.

## 13. Ghi nhớ

`requires static` khai báo một module dependency bắt buộc ở giai đoạn biên dịch nhưng tùy chọn trong runtime module graph. Nó hữu ích cho annotation, API hỗ trợ và integration mở rộng. Module tùy chọn có thể nằm trên module path nhưng vẫn không được phân giải nếu không có dependency runtime khác hoặc không được thêm bằng `--add-modules`.

Muốn sử dụng an toàn, hãy tách code phụ thuộc vào module tùy chọn, kiểm tra module graph trước khi nạp phần tích hợp và luôn kiểm thử cả cấu hình có lẫn không có dependency. Khi kiểu của dependency là một phần API cần truyền tới consumer, xem xét `requires static transitive`; trong các trường hợp còn lại, dùng directive đơn giản hơn.

Tài liệu tham khảo:

- [Java Language Specification, Java SE 21 — 7.7.1 Dependences](https://docs.oracle.com/javase/specs/jls/se21/jls21.pdf)
- [Java SE 21 API — ModuleDescriptor.Requires.Modifier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.Requires.Modifier.html)
- [Dev.java — Optional Dependencies with requires static](https://dev.java/learn/organizing/modules/optional-dependencies/)