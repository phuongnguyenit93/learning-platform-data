# Tài liệu cho module-info và package được công khai (Java 9+)

Từ Java 9, Java Platform Module System (JPMS) cho phép mỗi **named module** khai báo các phụ thuộc và phần API mà mô-đun cho phép bên ngoài sử dụng. Khi phát hành thư viện có `module-info.java`, tài liệu Javadoc phải giúp người dùng trả lời ba câu hỏi: **mô-đun này giải quyết việc gì**, **những package nào là API công khai**, và **phải dùng các kiểu/phương thức được công khai như thế nào**.

Hai tệp đặc biệt cần nắm vững là **`module-info.java`** và **`package-info.java`**. Tệp đầu mô tả mô-đun và các khai báo `requires`/`exports`/`opens`/`uses`/`provides`; tệp thứ hai chứa Javadoc của **một package cụ thể**. Tài liệu của class/interface/record vẫn viết ngay cạnh khai báo kiểu và thành viên. Tất cả các cơ chế này hiện vẫn được JDK hỗ trợ và là cách chuẩn để tài liệu hóa API của named module.

**Kết quả học tập:** bạn có thể viết Javadoc cho `module-info.java` và `package-info.java`, phân biệt package `exports` với package nội bộ, xây một module Java 17+ thật, chạy `javadoc` để xuất đúng phần API công khai, đọc các trang HTML được tạo và tránh để tài liệu vô tình hứa hẹn hỗ trợ những thành phần không thuộc API.

## 1. Ranh giới module, package và kiểu công khai

Đừng đánh đồng ba khái niệm:

| Cấp | Nơi khai báo/tài liệu | Mục đích | Trang Javadoc được sinh |
| --- | --- | --- | --- |
| **Module** | `module-info.java` | Nêu vai trò, hợp đồng tổng quan, phụ thuộc và các package xuất ra | `<module-name>/module-summary.html` |
| **Package** | `package-info.java` | Nêu chức năng, nguyên tắc sử dụng và quan hệ giữa các kiểu trong package | `<module-name>/<package-path>/package-summary.html` |
| **Kiểu và thành viên** | `GreetingService.java` cùng Javadoc `/** ... */` | Mô tả cách gọi, tham số, giá trị trả về, lỗi và các cam kết API | `<module-name>/<package-path>/GreetingService.html` |

Ví dụ module `com.example.greeting` có package `com.example.greeting.api` và `com.example.greeting.internal`. Nếu `module-info.java` chứa:

```java
module com.example.greeting {
    exports com.example.greeting.api;
}
```

thì các mô-đun khác đọc được những kiểu **public** của package `api`. Ngược lại, một class `public` trong package `internal` **vẫn không trở thành API công khai của named module** khi package không được `exports`. Từ khóa `public` là quy tắc truy cập ở cấp kiểu; `exports` mở ranh giới package ở cấp module. Cần **cả hai** để một kiểu public thông thường được mô-đun bên ngoài sử dụng trực tiếp.

Một quy tắc thực tế: viết Javadoc cho những điều **người tiêu dùng thư viện thực sự được phép phụ thuộc**. Nội dung trong package nội bộ có thể được ghi chú phục vụ bảo trì, nhưng đừng mô tả nó như một hợp đồng API ổn định.

## 2. Viết phần mô tả cho module-info.java

Lời mô tả Javadoc của module đặt **ngay trước khai báo `module`**, dùng cú pháp comment `/** ... */`. Đây là phần tài liệu tổng quan, không phải comment tùy ý nằm bên trong khối khai báo.

Ví dụ:

```java
/**
 * Cung cấp API tạo lời chào để ứng dụng khác sử dụng.
 *
 * <p>Chỉ các gói được khai báo {@code exports} mới thuộc API
 * công khai dành cho các mô-đun khác.
 *
 * @since 1.0
 */
module com.example.greeting {
    exports com.example.greeting.api;
}
```

Ý nghĩa:

- Câu đầu **tóm tắt đúng trách nhiệm của module**; Javadoc dùng câu đầu làm mô tả ngắn ở những nơi thích hợp.
- Phần sau giải thích hợp đồng sử dụng và phạm vi được công khai. Với một thư viện lớn, đây là nơi trình bày các nguyên tắc toàn module, liên kết đến package quan trọng hoặc hướng dẫn khởi đầu ngắn.
- `@since 1.0` là phiên bản **API của thư viện** bắt đầu cung cấp chức năng; không cần dùng số phiên bản JDK trừ khi đó đúng là quy ước phát hành của thư viện.
- `exports com.example.greeting.api;` là **khai báo Java thực sự được module system thực thi**; Javadoc không thể tự “mở” một package khi module chưa export.
- `module-info.java` là tệp Java đặc biệt, thường đặt ở gốc nguồn của named module. Cách sắp thư mục cụ thể phụ thuộc build tool, nhưng module descriptor không nằm trong package Java.

Những gì đáng viết trong module-level Javadoc: mục đích thư viện, điểm bắt đầu dùng API, các package chính, giả định/giới hạn có ảnh hưởng đến người gọi, quy tắc tương thích và liên kết tham khảo có giá trị. Không cần chép lại nguyên văn danh sách `exports`/`requires`: Javadoc đã có phần bảng khai báo module và trình biên dịch cũng hiểu chúng.

**Phân biệt tài liệu với hành vi:** sửa mô tả Javadoc không thay đổi khả năng truy cập ở runtime; thay đổi `exports`/`requires` trong descriptor có thể làm thay đổi API và tính tương thích, cho dù Javadoc chưa được cập nhật.

## 3. Viết package-info.java cho package API

Tệp `package-info.java` nằm **cùng thư mục với các lớp của package** và thường chỉ có Javadoc rồi đến khai báo `package ...;`:

```java
/**
 * API công khai để tạo lời chào.
 *
 * <p>Bắt đầu với {@link com.example.greeting.api.GreetingService}.
 * Các lớp trong gói internal không thuộc API được xuất.
 *
 * @since 1.0
 */
package com.example.greeting.api;
```

Tệp này mô tả **toàn bộ package**, ví dụ: các kiểu nào là entry point, cách kết hợp chúng, quy ước tham số, quy tắc thread safety, cách xử lý ngoại lệ hoặc điều kiện môi trường. Không nên viết một bản sao trùng lặp Javadoc của từng method.

Lưu ý:

- Dòng `package com.example.greeting.api;` xác định package đang được tài liệu hóa. Tên phải khớp thư mục nguồn và các class ở cùng package.
- Comment tài liệu `/** ... */` đặt **ngay trước khai báo package**. Comment `// ...` thông thường không trở thành đoạn mô tả Javadoc của package.
- Tag `{@link com.example.greeting.api.GreetingService}` tạo liên kết đến API tương ứng khi Javadoc giải được tham chiếu. Dùng `{@code ...}` để hiển thị tên lớp, phương thức hoặc đoạn mã như code mà không tạo link.
- Có thể đặt annotation cấp package tại đây, sau Javadoc và trước `package`, nếu API thực sự cần; đó là tính năng Java, không phải lý do phải tạo thêm class `PackageInfo`.
- Chỉ đặt một tệp `package-info.java` cho mỗi package trong cùng một tập mã nguồn có một khai báo package thống nhất.

**Không dùng package-info để “export” package.** Một package có mô tả rất đầy đủ vẫn là package nội bộ nếu descriptor không export nó. Ngược lại, một package đã export nhưng không có `package-info.java` vẫn là API công khai; nó chỉ thiếu ngữ cảnh giúp người dùng sử dụng đúng.

## 4. Javadoc tại kiểu và phương thức: chi tiết hợp đồng

Khi tài liệu module chỉ đúng package để bắt đầu, trang package chỉ đúng loại đối tượng để sử dụng, Javadoc tại **kiểu và method** phải trả lời các câu hỏi cụ thể của người gọi.

Ví dụ kiểu được export:

```java
package com.example.greeting.api;

import com.example.greeting.internal.GreetingFormatter;

/**
 * Tạo lời chào từ tên người nhận.
 *
 * @since 1.0
 */
public final class GreetingService {
    private GreetingService() { }

    /**
     * Tạo lời chào tiếng Việt.
     *
     * @param name tên người nhận, không được rỗng
     * @return lời chào đã chuẩn hóa
     * @throws IllegalArgumentException nếu {@code name} là null hoặc rỗng
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return GreetingFormatter.format(name.trim());
    }
}
```

Trong tài liệu của một API công khai, mô tả chính xác:

- `@param`: tham số có được là `null` hay chuỗi trắng không, chuẩn hóa/biến đổi như thế nào.
- `@return`: giá trị trả về và ý nghĩa, kể cả ranh giới dữ liệu trả về.
- `@throws`: điều kiện gây lỗi có ý nghĩa đối với người gọi.
- `@since`: mốc phiên bản **thư viện** bắt đầu có API.
- `{@link ...}`: liên kết tới kiểu hoặc method cùng API khi người đọc cần tìm hiểu thêm.

Nếu API có tính bất biến, thread safety, resource ownership, yêu cầu đóng tài nguyên, điều kiện blocking hoặc cách tương tác với service provider, nên mô tả ở lớp/phương thức phù hợp. Không đưa chi tiết nội bộ dễ thay đổi thành lời cam kết API.

**Javadoc không thay thế kiểm thử:** các điều kiện `@throws` hoặc ràng buộc đầu vào trong comment cần nhất quán với mã thực thi. Công cụ `javadoc` có thể bắt được lỗi tag/link nhưng không thể chứng minh mọi tuyên bố nghiệp vụ trong comment đều đúng.

## 5. Ví dụ hoàn chỉnh Java 17+: hai module, một package được export

Ví dụ dưới đây tự chứa đầy đủ mã nguồn, không cần dependency ngoài JDK. Module thư viện `com.example.greeting` export API, còn module ứng dụng `com.example.consumer` sử dụng API. Một helper có modifier `public` nhưng nằm trong package không được export để thấy rõ sự khác nhau giữa **public class** và **exported package**.

Cấu trúc tạo trong thư mục làm việc:

```text
javadoc-module-demo/
└── src/
    ├── com.example.greeting/
    │   ├── module-info.java
    │   └── com/example/greeting/
    │       ├── api/
    │       │   ├── package-info.java
    │       │   └── GreetingService.java
    │       └── internal/
    │           └── GreetingFormatter.java
    └── com.example.consumer/
        ├── module-info.java
        └── com/example/consumer/
            └── Main.java
```

### 5.1. Module thư viện

Tệp `src/com.example.greeting/module-info.java` chứa đúng code của mục 2:

```java
/**
 * Cung cấp API tạo lời chào để ứng dụng khác sử dụng.
 *
 * <p>Chỉ các gói được khai báo {@code exports} mới thuộc API
 * công khai dành cho các mô-đun khác.
 *
 * @since 1.0
 */
module com.example.greeting {
    exports com.example.greeting.api;
}
```

Tệp `src/com.example.greeting/com/example/greeting/api/package-info.java`:

```java
/**
 * API công khai để tạo lời chào.
 *
 * <p>Bắt đầu với {@link com.example.greeting.api.GreetingService}.
 * Các lớp trong gói internal không thuộc API được xuất.
 *
 * @since 1.0
 */
package com.example.greeting.api;
```

Tệp `src/com.example.greeting/com/example/greeting/api/GreetingService.java`:

```java
package com.example.greeting.api;

import com.example.greeting.internal.GreetingFormatter;

/**
 * Tạo lời chào từ tên người nhận.
 *
 * @since 1.0
 */
public final class GreetingService {
    private GreetingService() { }

    /**
     * Tạo lời chào tiếng Việt.
     *
     * @param name tên người nhận, không được rỗng
     * @return lời chào đã chuẩn hóa
     * @throws IllegalArgumentException nếu {@code name} là null hoặc rỗng
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return GreetingFormatter.format(name.trim());
    }
}
```

Tệp `src/com.example.greeting/com/example/greeting/internal/GreetingFormatter.java`:

```java
package com.example.greeting.internal;

/** Chi tiết triển khai không được export ra ngoài mô-đun. */
public final class GreetingFormatter {
    private GreetingFormatter() { }

    /** Trả về lời chào đã ghép. */
    public static String format(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Đây là chi tiết triển khai **được module của chính nó sử dụng**. Nó là class `public` vì lý do tổ chức mã ví dụ, nhưng một module khác không thể `import com.example.greeting.internal.GreetingFormatter;` theo quy tắc JPMS do `com.example.greeting.internal` không được export. Khi chạy Javadoc với chế độ công khai ở phần sau, trang internal này cũng không nằm trong tập trang API đầu ra.

### 5.2. Module tiêu thụ API

Tệp `src/com.example.consumer/module-info.java`:

```java
module com.example.consumer {
    requires com.example.greeting;
}
```

Tệp `src/com.example.consumer/com/example/consumer/Main.java`:

```java
package com.example.consumer;

import com.example.greeting.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        System.out.println(GreetingService.greet("Java"));
    }
}
```

Mô-đun consumer khai báo `requires com.example.greeting;` và dùng kiểu nằm trong package được export, nên biên dịch được. Nếu đổi import thành lớp trong `internal`, biên dịch từ **consumer module** sẽ bị từ chối vì package không được export, ngay cả khi class nội bộ được khai báo `public`.

### 5.3. Biên dịch và chạy

Đứng tại thư mục `javadoc-module-demo` (thư mục chứa `src`). Chạy đúng hai lệnh, dùng JDK 17+:

```bash
javac -encoding UTF-8 -d out --module-source-path src --module com.example.greeting,com.example.consumer
java --module-path out --module com.example.consumer/com.example.consumer.Main
```

Stdout chính xác:

```text
Xin chào, Java!
```

Giải thích:

- `--module-source-path src` nói với compiler cách tìm source theo thư mục tên module dưới `src`.
- `--module com.example.greeting,com.example.consumer` chỉ định hai module cần biên dịch; output được đặt vào `out`.
- `java --module-path out` làm runtime tìm module đã biên dịch ở `out`.
- `--module com.example.consumer/com.example.consumer.Main` chọn module và main class để chạy.
- Trong mã, class của package nội bộ vẫn có thể được gọi **bên trong cùng module**; chính ranh giới giữa hai module mới kích hoạt giới hạn `exports`.

## 6. Sinh Javadoc công khai cho module

Ở cùng thư mục chứa `src`, chạy:

```bash
javadoc -quiet -Xdoclint:all -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs --module-source-path src --module com.example.greeting --show-packages exported --show-types public --show-members public --show-module-contents api
```

Đây là **một dòng lệnh hoàn chỉnh**, chạy được cả trong shell Unix và PowerShell khi gọi từ thư mục dự án. Nó chỉ yêu cầu JDK có công cụ `javadoc`. Không cần chạy ứng dụng trước khi sinh docs, nhưng ví dụ đã biên dịch/chạy để kiểm tra chính xác mối liên hệ module.

| Tham số | Ý nghĩa thực tế |
| --- | --- |
| `-d docs` | Thư mục chứa HTML đã tạo |
| `--module-source-path src` | Cấu trúc source root trong đó mỗi thư mục cấp đầu là một named module |
| `--module com.example.greeting` | Chỉ xuất Javadoc cho **module thư viện**, không sinh tài liệu cho consumer |
| `--show-packages exported` | Chọn các package được export; loại các package nội bộ khỏi tài liệu API này |
| `--show-types public` | Chọn các kiểu public trong những package được chọn |
| `--show-members public` | Chọn thành viên public; một thư viện cũng có thể muốn dùng `protected` khi public API được thiết kế cho kế thừa |
| `--show-module-contents api` | Tập trung trang module vào các nội dung API |
| `-Xdoclint:all` | Bật kiểm tra Javadoc nghiêm ngặt để phát hiện nhiều vấn đề cú pháp, HTML và tham chiếu |
| `-encoding`, `-docencoding`, `-charset UTF-8` | Đọc nguồn và phát hành HTML sử dụng UTF-8, giữ đúng dấu tiếng Việt |
| `-quiet` | Hạn chế thông báo tiến trình, giúp dễ thấy cảnh báo và lỗi |

Công cụ Javadoc **được kiểm chứng chạy thành công cùng `-Xdoclint:all`** với toàn bộ ví dụ trên bằng JDK 24.

### 6.1. Kiểm tra các trang đầu ra

Khi lệnh thành công, các đường dẫn đáng kiểm tra gồm:

```text
docs/
├── index.html
└── com.example.greeting/
    ├── module-summary.html
    └── com/example/greeting/api/
        ├── package-summary.html
        └── GreetingService.html
```

- `docs/com.example.greeting/module-summary.html`: có mô tả từ comment của `module-info.java` và danh sách package/API xuất ra.
- `docs/com.example.greeting/com/example/greeting/api/package-summary.html`: có mô tả từ `package-info.java` và kiểu `GreetingService`.
- `docs/com.example.greeting/com/example/greeting/api/GreetingService.html`: có mô tả kiểu và phương thức `greet`, `@param`, `@return` và `@throws`.
- `docs/com.example.greeting/com/example/greeting/internal/GreetingFormatter.html`: **không xuất hiện** trong bản API Javadoc được tạo bằng tùy chọn `--show-packages exported`.

Đây là **kết quả đã được kiểm chứng bằng công cụ JDK 24** với cấu trúc ví dụ đã cho. Các tệp CSS/JS, chỉ mục và bố cục trang còn phụ thuộc phiên bản Javadoc, vì vậy đừng dùng số tệp hoặc cấu trúc CSS cụ thể làm hợp đồng ổn định.

### 6.2. Nếu cố ý cần tài liệu nội bộ thì sao?

Trong tài liệu dành riêng cho người bảo trì, có thể dùng:

```bash
javadoc -quiet -Xdoclint:all -d docs-internal --module-source-path src --module com.example.greeting --show-packages all --show-types public --show-members public --show-module-contents all
```

Đây là **chế độ tài liệu nội bộ** để cân nhắc, không phải cách xuất SDK công khai cho người tiêu dùng. `--show-packages all` mở phạm vi package cần tạo tài liệu; `--show-module-contents all` yêu cầu nội dung module chi tiết hơn. Hai tùy chọn này thay đổi **tập trang Javadoc**, **không thay đổi** descriptor `module-info.java` và không làm package nội bộ trở nên import được từ module khác.

Nếu dùng tool Gradle/Maven/IDE để sinh docs thay vì gọi trực tiếp `javadoc`, hãy ánh xạ các tùy chọn này vào cấu hình build thực tế và xác minh bộ source/module path đúng với cách dự án đang tổ chức. Ví dụ `src/<module-name>/...` ở đây là cấu trúc độc lập để học, không bắt buộc mọi dự án dùng cấu trúc giống hệt.

## 7. Nắm các ranh giới được công khai trong JPMS

### 7.1. exports, exports ... to và opens

| Khai báo | Quyền truy cập chính | Tác động lên tài liệu |
| --- | --- | --- |
| `exports p.api;` | Các module đọc được module này có thể truy cập kiểu public của `p.api` theo luật Java | Package thuộc API xuất công khai |
| `exports p.spi to partner.module;` | Chỉ module được nêu trong danh sách mới được cấp qualified export | Hợp đồng dành cho nhóm consumer được chỉ định, không phải API chung cho mọi module |
| `opens p.model;` | Cho phép reflection sâu vào package khi đáp ứng các quy tắc runtime | Không đồng nghĩa cho code ngoài module compile với kiểu public như `exports` |
| Package tồn tại nhưng không có `exports`/`opens` | Package được đóng gói trong module nhưng không được công khai qua các directive đó | Không mặc định biến thành package công khai chỉ vì có JavaDoc hoặc class `public` |

**Phân biệt với `requires`:** `requires other.module;` nói module **phụ thuộc** module nào, không chỉ ra package nào của module hiện tại được xuất ra. `requires transitive` có thể làm module khác đọc được dependency transitively; chỉ dùng khi chữ ký API công khai và thiết kế module thực sự yêu cầu, không chỉ vì muốn hiện thêm module trong Javadoc.

**Phân biệt với `open module`:** đây là chế độ mở phục vụ reflection, không có nghĩa tự động export mọi package theo quy tắc truy cập kiểu thời gian biên dịch. Tên package có thể chứa kiểu `public` nhưng vẫn không thuộc API compile-time của module ngoài.

### 7.2. Javadoc cho dịch vụ uses/provides

Một module cung cấp hoặc dùng dịch vụ qua `ServiceLoader` có thể có directive `uses ServiceType;` và `provides ServiceType with ImplType;`. Trong **comment Javadoc của module-info.java**, các tag còn được hỗ trợ từ Java 9:

- `@uses fully.qualified.ServiceType mô tả`: module dùng dịch vụ gì, yêu cầu đặc tính nào hoặc hành vi khi thiếu provider.
- `@provides fully.qualified.ServiceType mô tả`: module cung cấp implementation nào và cách người dùng tìm/lấy provider.

Hai tag này có ý nghĩa **tài liệu hóa** các service declaration tương ứng; chúng không thay thế code `uses`/`provides` trong module descriptor. Chỉ thêm khi module **thực sự** có service; ví dụ thư viện lời chào ở trên không dùng SPI, vì vậy không có các tag này.

Đối với library API công khai, người đọc cần biết phần nào là module service contract, phần nào là implementation detail. Có thể tài liệu hóa các yêu cầu về lifecycle, resource usage hoặc tính thread safe của service, nhưng không tự tuyên bố một implementation nội bộ là thành phần công khai trừ khi đó là hợp đồng được thiết kế có chủ ý.

## 8. Viết nội dung ở đúng cấp độ

| Nội dung | Nên đặt ở đâu? | Vì sao? |
| --- | --- | --- |
| Mục đích và cam kết lớn của module | `module-info.java` | Là điểm mở đầu của tài liệu module |
| Danh sách các package được công khai | Khai báo `exports` trong `module-info.java` | Source of truth cho module system và Javadoc |
| Cách phối hợp các kiểu trong package, use case của package | `package-info.java` | Người dùng đọc trang package để hiểu nhóm API |
| Ý nghĩa của class/interface, thread safety và lifecycle | Comment ngay trước khai báo kiểu | Tránh cam kết nằm xa API tương ứng |
| Hợp đồng tham số, kết quả và lỗi | Comment của constructor/method | Đảm bảo người gọi tìm được ngay tại mục cần gọi |
| Mô tả module service thực sự có `uses`/`provides` | Comment module với `@uses`/`@provides` | Liên kết đúng service với module |
| Hướng dẫn dài/kiến trúc bổ trợ | Tài liệu bổ trợ được liên kết từ module/package | Giữ trang Javadoc đủ tập trung để tra cứu |

Khi dùng cú pháp Javadoc, giữ câu đầu làm tóm tắt có nghĩa và ưu tiên link đến phần tử thực sự tồn tại. Ví dụ `{@link com.example.greeting.api.GreetingService}` tạo link đến class; `{@code exports}` biểu diễn code mà không yêu cầu resolver tìm một phần tử tên “exports”. Khi muốn nêu phiên bản thư viện, dùng `@since` theo lịch sử phát hành thực tế, tránh ghi một mốc ngẫu nhiên không khớp mã.

Một page Javadoc đẹp nhưng **sai phạm vi API** vẫn có thể gây hại: consumer nghĩ họ được phép import package nội bộ hoặc tin tưởng các chi tiết triển khai chưa được cam kết. Vì vậy kiểm tra `module-info.java`, trang module/package được tạo và khả năng biên dịch từ module consumer là ba phép kiểm bổ trợ cho nhau.

## 9. Kiểm tra chất lượng tài liệu khi phát hành

Một quy trình hợp lý cho thư viện có named module:

1. **Chốt API của module:** rà `exports`, qualified exports, các kiểu public và những dependency thực sự xuất hiện trong public signatures.
2. **Viết tài liệu module:** mục đích, cấu trúc API và điểm bắt đầu. Viết `package-info.java` ở từng package mà người dùng cần ngữ cảnh sử dụng.
3. **Bổ sung chi tiết trên kiểu/method:** điều kiện đầu vào, kết quả, ngoại lệ và các cam kết có thể kiểm thử.
4. **Sinh docs ở chế độ API:** `--show-packages exported`, phạm vi type/member và `--show-module-contents api` phù hợp.
5. **Chạy DocLint:** bật `-Xdoclint:all`; xử lý liên kết không giải được, tag sai vị trí, comment thiếu thông tin cần thiết hoặc HTML không đúng.
6. **Mở HTML thật:** kiểm tra trang module, package, kiểu, các liên kết và sơ đồ phân cấp được sinh; xác nhận package nội bộ không xuất hiện ngoài ý muốn.
7. **Biên dịch một consumer module:** kiểm tra public API thực sự sử dụng được theo `requires`/`exports`; thêm kiểm thử hành vi cho các cam kết mà Javadoc mô tả.
8. **Duy trì cùng phiên bản thư viện:** tài liệu cần được xây từ cùng revision/source với binary phát hành; cập nhật Javadoc và release note khi API công khai thay đổi.

Một lựa chọn chất lượng khác là sinh docs nội bộ để người bảo trì tra cứu, nhưng **xuất bản nhầm bản internal** có thể khiến người dùng phụ thuộc các tên không ổn định. Nên đặt thư mục artifact rõ ràng và chỉ phân phối bản API khi làm SDK public.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đặt Javadoc sau `module ... {` hoặc trước một directive `exports` thay vì trước `module` | Không trở thành mô tả chính của module | Đặt `/** ... */` ngay trước khai báo `module` |
| Có `package-info.java` nhưng quên `exports` | Package vẫn không truy cập được từ module consumer | Rà descriptor; chỉ export package được thiết kế làm API |
| Nghĩ class `public` trong package internal đương nhiên import được | Compile lỗi ở module bên ngoài | Kiểm tra cả modifier của kiểu và export của package |
| Nghĩ `opens p;` tương đương `exports p;` | Hiểu sai phản chiếu và compile-time accessibility | Dùng `exports` cho public API; `opens` phục vụ reflection đúng phạm vi |
| Dùng comment `// ...` thay Javadoc `/** ... */` | Không sinh description như dự kiến | Dùng documentation comment đúng chỗ |
| Đặt mô tả package trên một class tùy ý | Trang package thiếu mô tả, nội dung ở sai nơi | Dùng `package-info.java` |
| Tạo một class `PackageInfo` để mô tả package | Không phải cú pháp package Javadoc chuẩn | Viết `package-info.java` với khai báo package |
| Dùng `{@link ...}` đến kiểu ngoài module hoặc package không hiện trong docs | Link không được giải hoặc tạo tài liệu khó theo dõi | Kiểm tra link với DocLint và phạm vi Javadoc được sinh |
| Dùng `-private`/`--show-packages all` khi xuất SDK public | Có thể công bố API nội bộ ngoài ý muốn | Chọn `--show-packages exported` và visibility phù hợp |
| Cho rằng `--show-packages all` làm package được export | Nhầm công cụ tài liệu với Java access control | Sửa `module-info.java` nếu cần mở API thực sự |
| Quên `-encoding UTF-8` với chú thích tiếng Việt | Có thể lỗi ký tự theo môi trường | Thống nhất encoding nguồn và đầu ra |
| Viết `@since 9` chỉ vì đây là tính năng JPMS | Lịch sử phát hành thư viện không chính xác | Đặt `@since` theo phiên bản sản phẩm thực tế |
| Bỏ qua cảnh báo DocLint vì trang vẫn sinh | Thiếu link, hợp đồng và cấu trúc tài liệu bị lỗi | Xử lý cảnh báo có ý nghĩa và kiểm tra HTML sinh ra |
| Cho rằng Javadoc chứng minh API đúng hành vi | Comment có thể khác code | Kết hợp unit test và consumer compilation |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Named module có `public class InternalFormatter` nhưng package chứa class không xuất hiện trong `exports`. Module ngoài có import trực tiếp không?  
**Đáp án:** Không theo quy tắc truy cập bình thường của JPMS. Modifier `public` không vượt qua ranh giới `exports`.

**Câu 2.** Muốn tạo trang mô tả tổng quan của cả named module, cần đặt comment ở đâu?  
**Đáp án:** Trong `module-info.java`, dùng `/** ... */` ngay trước khai báo `module ... { }`.

**Câu 3.** Muốn mô tả nhóm kiểu trong package API và tạo liên kết từ trang package sang class chính, dùng tệp nào?  
**Đáp án:** `package-info.java` với `package ...;` và tag `{@link ...}` tương ứng.

**Câu 4.** `--show-packages all` có tự mở quyền import package nội bộ không?  
**Đáp án:** Không. Nó chỉ đổi phạm vi tài liệu được tạo; quyền truy cập thật nằm ở descriptor và quy tắc ngôn ngữ Java.

**Câu 5.** Vì sao nên biên dịch cả một consumer module?  
**Đáp án:** Để kiểm tra `requires`/`exports` và khả năng sử dụng API từ bên ngoài, điều mà việc nhìn HTML Javadoc một mình không bảo đảm.

**Câu 6.** Hai tag `@uses` và `@provides` dùng ở cấp nào?  
**Đáp án:** Chúng tài liệu hóa service trong comment module, đi cùng directive `uses`/`provides` tương ứng; không thay thế các directive.

**Câu 7.** Nếu muốn tài liệu hóa API dành cho kế thừa, có nên luôn đặt `--show-members public`?  
**Đáp án:** Không nhất thiết. Thành viên `protected` có thể là một phần hợp đồng extension của public class; chọn visibility `protected` khi nó thuộc API thiết kế cho subclass. Bản ví dụ chỉ có method public nên dùng `public` để rõ phạm vi.

## Tài liệu chuẩn và công cụ còn áp dụng

- [JDK 27 — The javadoc Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): `--module-source-path`, `--module`, `--show-packages`, `--show-types`, `--show-members` và tùy chọn sinh tài liệu.
- [JDK 26 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): cú pháp `/** ... */`, `@since`, `@param`, `@uses`, `@provides`, `{@link ...}`.
- [JDK 26 — The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cách bố trí source của module và biên dịch với `--module-source-path`.
- [JDK 26 — Java Language Specification, Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html): ý nghĩa của `requires`, `exports`, `opens`, `uses` và `provides`.
- [JDK 25 — API của jdk.javadoc.doclet](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.javadoc/jdk/javadoc/doclet/package-summary.html): nguyên tắc các tùy chọn phạm vi tài liệu API.

**Điều cần nhớ:** `module-info.java` mô tả và khai báo **ranh giới module**, `package-info.java` giải thích **package mà người dùng được phép dùng**, còn Javadoc của các kiểu/method giải thích **cách dùng chi tiết**. Một bộ tài liệu công khai đúng phải phản ánh chính xác `exports` và được kiểm chứng bằng cả HTML sinh ra lẫn khả năng biên dịch của module consumer.
