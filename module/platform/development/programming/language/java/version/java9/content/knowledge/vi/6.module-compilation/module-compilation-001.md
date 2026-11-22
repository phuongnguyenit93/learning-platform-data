# Thiết lập `--module-path` và `--module-source-path`

## Mục tiêu

Khi biên dịch ứng dụng dùng Java Platform Module System (JPMS), trình biên dịch cần biết hai loại đầu vào: mã nguồn của các module đang được biên dịch và các module đã được biên dịch mà chúng phụ thuộc. Hai tùy chọn `--module-source-path` và `--module-path` giải quyết hai nhu cầu khác nhau.

- `--module-source-path` chỉ vị trí mã nguồn của một hoặc nhiều module để `javac` tìm `module-info.java` và các tệp `.java` tương ứng.
- `--module-path` chỉ vị trí các module đã có thể được phân giải, chẳng hạn thư mục chứa exploded modules hoặc các modular JAR. Tùy chọn này được dùng khi biên dịch và khi khởi chạy.

Hiểu đúng hai đường dẫn giúp tránh lỗi `module not found`, tránh đặt nhầm thư viện lên class path và giữ cho cấu hình build giống cấu hình runtime.

## 1. Phân biệt các loại đường dẫn

| Tùy chọn | Dữ liệu được tìm | Thời điểm dùng |
|---|---|---|
| `--module-source-path` | Mã nguồn của các module, gồm `module-info.java` và các lớp Java | Biên dịch bằng `javac` |
| `--module-path` (`-p`) | Các module đã biên dịch: exploded module hoặc modular JAR | Biên dịch và chạy |
| `--class-path` (`-cp`, `-classpath`) | Các lớp và JAR thuộc class path/unnamed module | Biên dịch và chạy ứng dụng class path hoặc thư viện class path |
| `--source-path` | Mã nguồn Java thông thường không được tổ chức như một tập module | Biên dịch mã nguồn thông thường |

`--module-source-path` không thay thế `--module-path`: một đường dẫn chứa `.java` để biên dịch, đường dẫn còn lại chứa module mà module đang biên dịch cần đọc. Tương tự, `--module-path` không phải nơi đặt mã nguồn của module chưa biên dịch.

Với một module có tên, chỉ thị `requires` được phân giải qua module system. Đặt một JAR thông thường trên `--class-path` không làm cho nó tự động đáp ứng một `requires` có tên. Nếu một thư viện chưa có module descriptor, hãy kiểm tra cách JDK nhận diện thư viện đó trước khi chọn cách đóng gói và đường dẫn.

## 2. Cấu trúc thư mục nguồn cho nhiều module

Với một source root chung, cấu trúc dễ quản lý là thư mục con của source root mang tên module. Bên trong mỗi thư mục module có `module-info.java` ở gốc và các package theo cấu trúc Java thông thường.

```text
project/
├── src/
│   ├── com.example.model/
│   │   ├── module-info.java
│   │   └── com/example/model/Greeting.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
└── out/
```

Ví dụ `src/com.example.app/module-info.java` khai báo `module com.example.app { ... }`. Tên thư mục module phải khớp tên module trong descriptor. Package vẫn nằm trong các thư mục con như `com/example/app`.

## 3. Biên dịch nhiều module từ mã nguồn

Giả sử module `com.example.model` cung cấp API `Greeting`, còn module `com.example.app` gọi API đó.

**`src/com.example.model/module-info.java`**

```java
module com.example.model {
    exports com.example.model;
}
```

**`src/com.example.model/com/example/model/Greeting.java`**

```java
package com.example.model;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Hello from JPMS";
    }
}
```

**`src/com.example.app/module-info.java`**

```java
module com.example.app {
    requires com.example.model;
}
```

**`src/com.example.app/com/example/app/Main.java`**

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println(com.example.model.Greeting.message());
    }
}
```

### Lệnh biên dịch

Tạo thư mục output trước khi gọi compiler:

```powershell
New-Item -ItemType Directory -Force out
javac --module-source-path src -d out -m com.example.model,com.example.app
```

Trên Linux hoặc macOS, lệnh tạo thư mục tương đương là `mkdir -p out`; lệnh `javac` giữ nguyên.

Ý nghĩa các phần:

- `--module-source-path src`: yêu cầu `javac` tìm các module nguồn trong source root `src`.
- `-d out`: ghi các tệp `.class` và `module-info.class` vào thư mục output `out`.
- `-m com.example.model,com.example.app`: biên dịch hai module được nêu tên. Danh sách tên module được phân tách bằng dấu phẩy.

Sau khi biên dịch, output có cấu trúc dạng:

```text
out/
├── com.example.model/
│   ├── module-info.class
│   └── com/example/model/Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
```

Vì hai module nguồn đều nằm dưới cùng source root, `javac` có thể tìm descriptor và mã nguồn của dependency trong module source path. Ở trường hợp này không cần thêm `--module-path` cho `com.example.model` vì nó đang được biên dịch từ source tree trong cùng lệnh.

## 4. Dùng `--module-path` khi dependency đã được đóng gói

Trong dự án thực tế, một thư viện thường được build trước và cung cấp dưới dạng modular JAR. Khi đó module đang biên dịch lấy mã nguồn từ `--module-source-path`, còn dependency đã đóng gói được tìm qua `--module-path`.

Trước hết, tạo JAR từ output của module `com.example.model`: 

```powershell
New-Item -ItemType Directory -Force lib
jar --create --file lib/com.example.model.jar -C out/com.example.model .
```

Trong lệnh này, `-C out/com.example.model .` đưa nội dung của exploded module vào gốc JAR, bao gồm `module-info.class`.

Giả sử mã nguồn ứng dụng được đặt riêng trong `app-src/com.example.app/`, gồm `module-info.java` và `com/example/app/Main.java`. Biên dịch riêng module ứng dụng:

```powershell
New-Item -ItemType Directory -Force out-app
javac --module-path lib --module-source-path app-src -d out-app -m com.example.app
```

Ở đây:

- `--module-path lib`: tìm module `com.example.model` trong modular JAR nằm trong thư mục `lib`.
- `--module-source-path app-src`: chỉ tìm mã nguồn của module ứng dụng.
- `-m com.example.app`: yêu cầu compiler biên dịch module ứng dụng.

Trên Linux hoặc macOS, hai lệnh tạo thư mục có thể viết là `mkdir -p lib` và `mkdir -p out-app`.

## 5. Dùng `--module-path` khi chạy ứng dụng

`--module-source-path` chỉ phục vụ bước biên dịch. Khi chạy, JVM cần các module đã biên dịch, vì vậy cấu hình runtime dùng `--module-path`.

Với ví dụ đã biên dịch tất cả module vào `out`, chạy:

```bash
java --module-path out -m com.example.app/com.example.app.Main
```

Stdout:

```text
Hello from JPMS
```

Cú pháp `-m module/class` chỉ rõ module gốc và lớp có phương thức `main`. Trong ví dụ, module gốc là `com.example.app`, còn lớp chạy là `com.example.app.Main`.

Nếu ứng dụng đã biên dịch riêng và dependency nằm trong `lib`, runtime phải đưa cả output ứng dụng và thư viện lên module path.

PowerShell trên Windows:

```powershell
java --module-path "out-app;lib" -m com.example.app/com.example.app.Main
```

Linux hoặc macOS:

```bash
java --module-path "out-app:lib" -m com.example.app/com.example.app.Main
```

Đường dẫn module path là danh sách nhiều mục. Dấu phân cách giữa các mục phụ thuộc hệ điều hành: Windows dùng dấu chấm phẩy `;`, Linux và macOS dùng dấu hai chấm `:`. Dấu phẩy trong `-m module.one,module.two` là dấu phân cách tên module, không phải dấu phân cách đường dẫn.

## 6. Kết hợp nhiều thư mục hoặc JAR trên module path

`--module-path` nhận một hoặc nhiều vị trí. Một mục có thể là thư mục chứa các exploded modules hoặc modular JAR; nhiều mục được ghép thành một danh sách theo quy tắc phân cách của hệ điều hành.

Ví dụ trên Windows:

```powershell
javac --module-path "lib;vendor\modules" --module-source-path src -d out -m com.example.app
java --module-path "out;lib;vendor\modules" -m com.example.app/com.example.app.Main
```

Ví dụ trên Linux hoặc macOS:

```bash
javac --module-path "lib:vendor/modules" --module-source-path src -d out -m com.example.app
java --module-path "out:lib:vendor/modules" -m com.example.app/com.example.app.Main
```

Nếu đường dẫn có khoảng trắng, đặt toàn bộ giá trị của tùy chọn trong dấu nháy phù hợp với shell. Trên PowerShell, dấu nháy kép thường là cách dễ đọc; trên shell POSIX có thể dùng dấu nháy đơn hoặc kép.

## 7. Chẩn đoán lỗi thường gặp

### `module not found` khi biên dịch

Nguyên nhân thường là module được yêu cầu không có trong module source path hoặc module path. Kiểm tra:

1. Tên trong `requires` có khớp tên module trong `module-info.java` của dependency không?
2. Dependency là source module thì thư mục module có nằm dưới `--module-source-path` không?
3. Dependency đã biên dịch thì thư mục chứa exploded module hoặc modular JAR có nằm trên `--module-path` không?
4. Modular JAR có thực sự chứa `module-info.class` và tên module mong đợi không?

### `module ... not found in module source path`

Compiler không tìm thấy source module được chỉ định bằng `-m`. Kiểm tra source root và cấu trúc thư mục `src/<module-name>/module-info.java`; tên module trong đường dẫn phải khớp tên module được yêu cầu.

### `FindException` khi chạy

Compiler có thể đã tìm thấy dependency trong môi trường build, nhưng lệnh `java` lại thiếu dependency trên module path runtime. So sánh cấu hình module path khi biên dịch và khi chạy. Mọi dependency bắt buộc để phân giải module gốc đều phải có mặt trong cấu hình runtime.

### Package không hiển thị hoặc module không đọc module khác

Đây có thể là lỗi quan hệ module chứ không phải lỗi đường dẫn. Kiểm tra `requires` trong module gọi và `exports` của package thuộc module cung cấp. `--module-path` chỉ giúp tìm module; nó không tự cấp quyền đọc hoặc xuất package.

### Xác minh nội dung một modular JAR

Dùng lệnh sau để xem tên module và descriptor mà JAR công bố:

```bash
jar --describe-module --file lib/com.example.model.jar
```

Để xem JVM phân giải module nào khi chạy, thêm `--show-module-resolution` vào lệnh `java`. Đây là cách hữu ích để đối chiếu module gốc và các dependency thực tế được tìm thấy.

## 8. Những nhầm lẫn cần tránh

- Đưa thư mục chứa mã nguồn vào `--module-path`: mã nguồn module cần được tìm qua `--module-source-path` khi dùng cách biên dịch nhiều module.
- Đưa modular JAR vào `--module-source-path`: JAR đã biên dịch cần được tìm qua `--module-path`.
- Chỉ cấu hình module path khi biên dịch: runtime có module path riêng, phải chứa các dependency bắt buộc khi ứng dụng khởi chạy.
- Đưa JAR cần thiết cho `requires` lên class path và kỳ vọng nó được phân giải như named module: class path và module path có vai trò khác nhau.
- Dùng dấu phân cách sai hệ điều hành: Windows dùng `;`, Linux/macOS dùng `:` cho nhiều mục trong path.
- Nhầm danh sách module của `-m` với danh sách path: `-m` phân tách module bằng dấu phẩy; module path phân tách bằng ký tự riêng của hệ điều hành.
- Bỏ qua việc tạo thư mục output: tạo `out` hoặc `out-app` trước khi dùng làm đích `-d` để các lệnh ví dụ có thể chạy độc lập.

## 9. Checklist cấu hình build và runtime

- [ ] Mỗi module nguồn có `module-info.java` ở đúng thư mục module.
- [ ] Source root được truyền vào `--module-source-path` và cấu trúc thư mục khớp tên module.
- [ ] Các dependency đã biên dịch được đặt trong thư mục/JAR trên `--module-path`.
- [ ] Các module cần biên dịch được nêu rõ bằng `-m`.
- [ ] Output directory tồn tại trước khi truyền cho `-d`.
- [ ] Lệnh chạy dùng `--module-path` chứa module ứng dụng và mọi dependency bắt buộc.
- [ ] Dấu phân cách module path phù hợp với Windows hoặc Linux/macOS.
- [ ] Lệnh build và lệnh chạy đã được kiểm tra trong môi trường triển khai thực tế.

## Tài liệu tham khảo

1. [The javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html), mô tả `--module-path`, `--module-source-path`, `-d` và `-m`.
2. [The java Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html), mô tả module path và cú pháp khởi chạy module.
3. [The jar Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html), cách tạo và kiểm tra modular JAR.
4. [Java Language Specification, Java SE 24 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se24/html/jls-7.html#jls-7.7), cấu trúc module descriptor và chỉ thị `requires`.