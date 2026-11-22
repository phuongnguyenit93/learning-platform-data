# Biên dịch nhiều module bằng javac --module-source-path

## 1. Mục tiêu

Khi một dự án Java được chia thành nhiều named module, việc biên dịch không còn đơn giản là đưa tất cả file `.java` vào một lệnh `javac` như dự án classpath truyền thống. Compiler cần biết file nguồn thuộc module nào, module descriptor nằm ở đâu và dependency giữa các module được giải quyết ra sao.

Tùy chọn `--module-source-path` cho `javac` biết nơi chứa source tree của nhiều module. Kết hợp với `--module` hoặc `-m`, compiler có thể biên dịch các module được chỉ định từ một cấu trúc thư mục chung.

Bài này tập trung vào cách tổ chức source tree, cú pháp lệnh biên dịch, thư mục output và cách kết hợp source module với dependency đã biên dịch.

Sau bài này, bạn có thể:

- Tổ chức mã nguồn nhiều module theo tên module.
- Dùng `--module-source-path` để compiler tìm `module-info.java` và source của từng module.
- Dùng `-m` để chọn module cần biên dịch.
- Dùng `-d` để đặt output và `--module-path` cho dependency đã biên dịch.
- Nhận biết những lỗi thường gặp khi biên dịch modular project.

## 2. Ví dụ cấu trúc source tree

Giả sử ứng dụng có hai module:

- `com.example.api`: cung cấp API.
- `com.example.app`: sử dụng API.

Một cấu trúc thư mục đơn giản:

```text
project/
├── src/
│   ├── com.example.api/
│   │   ├── module-info.java
│   │   └── com/
│   │       └── example/
│   │           └── api/
│   │               └── Greeting.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── app/
│                   └── Main.java
└── out/
```

Điểm cần nhớ:

- `src` là module source path root.
- Mỗi thư mục con trực tiếp đại diện cho một module và tên thư mục khớp với tên module trong `module-info.java`.
- Bên trong thư mục module, cấu trúc package vẫn đi theo đường dẫn package thông thường.
- Mỗi named module có một `module-info.java` ở gốc source tree của module.

Ví dụ module API:

```java
// src/com.example.api/module-info.java
module com.example.api {
    exports com.example.api;
}
```

```java
// src/com.example.api/com/example/api/Greeting.java
package com.example.api;

public final class Greeting {
    public static String message() {
        return "Hello from API";
    }
}
```

Module ứng dụng:

```java
// src/com.example.app/module-info.java
module com.example.app {
    requires com.example.api;
}
```

```java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Tên thư mục module và tên khai báo trong `module-info.java` phải nhất quán để compiler tìm đúng source của module.

## 3. Cú pháp cơ bản của --module-source-path

Cú pháp tổng quát:

```bash
javac --module-source-path <module-source-path> -d <output-directory> --module <module-name>[,<module-name>...]
```

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `javac` | Java compiler. |
| `--module-source-path` | Chỉ định vị trí hoặc mẫu đường dẫn chứa source của các module. |
| `-d` | Chỉ định thư mục ghi file đã biên dịch. |
| `--module` hoặc `-m` | Chỉ định một hay nhiều module cần biên dịch. |

Với cấu trúc ở phần trước, chạy từ thư mục `project`:

```bash
javac --module-source-path src -d out --module com.example.api,com.example.app
```

Dạng viết ngắn:

```bash
javac --module-source-path src -d out -m com.example.api,com.example.app
```

Hai lệnh tương đương vì `-m` là dạng viết tắt của tùy chọn `--module` trong javac.

Lệnh trên cho compiler biết source tree của các module nằm dưới `src`, output đặt trong `out`, và hai module được yêu cầu biên dịch là `com.example.api` cùng `com.example.app`.

Khi biên dịch một tập module có quan hệ phụ thuộc, hãy bảo đảm source của các module liên quan đều có thể được tìm thấy và các module được chọn được đưa vào lệnh biên dịch theo đúng phạm vi dự án.

## 4. Kết quả sau khi biên dịch

Với tùy chọn `-d out`, compiler tạo output theo từng module. Cấu trúc kết quả có dạng:

```text
out/
├── com.example.api/
│   ├── module-info.class
│   └── com/
│       └── example/
│           └── api/
│               └── Greeting.class
└── com.example.app/
    ├── module-info.class
    └── com/
        └── example/
            └── app/
                └── Main.class
```

Mỗi module có thư mục output riêng. File `module-info.class` chứa module descriptor đã biên dịch; các class còn lại nằm theo package.

Có thể chạy ứng dụng bằng module path trỏ tới thư mục output:

```bash
java --module-path out --module com.example.app/com.example.app.Main
```

Dạng ngắn:

```bash
java -p out -m com.example.app/com.example.app.Main
```

Ở lệnh chạy, phần trước dấu `/` là tên module; phần sau là tên đầy đủ của main class. Đây là cú pháp của lệnh `java`, không phải cú pháp chọn module để biên dịch của `javac`.

## 5. Chỉ định module source path bằng pattern

Khi source tree không đặt trực tiếp dưới một thư mục module source root đơn giản, `--module-source-path` hỗ trợ pattern có dấu `*` để đại diện cho tên module.

Ví dụ cấu trúc:

```text
project/
└── src/
    ├── com.example.api/
    │   └── main/
    │       └── java/
    │           ├── module-info.java
    │           └── com/example/api/Greeting.java
    └── com.example.app/
        └── main/
            └── java/
                ├── module-info.java
                └── com/example/app/Main.java
```

Pattern `src/*/main/java` đại diện cho source root của từng module:

```bash
javac --module-source-path "src/*/main/java" -d out -m com.example.api,com.example.app
```

Dấu `*` được javac dùng như phần tên module trong module source path pattern. Đặt pattern trong dấu nháy giúp shell chuyển nguyên pattern cho compiler thay vì tự diễn giải ký tự wildcard.

Nếu dự án có nhiều source root, module source path cũng có thể chứa danh sách đường dẫn theo quy tắc phân tách path của hệ điều hành. Trên Windows, path-list thường dùng dấu chấm phẩy; trên Linux/macOS thường dùng dấu hai chấm. Khi viết lệnh chạy trên nhiều hệ điều hành, cần chú ý sự khác biệt này.

## 6. Chọn module nào để biên dịch?

Dùng `--module` hoặc `-m` để nêu rõ module cần biên dịch:

```bash
javac --module-source-path src -d out -m com.example.api
```

Lệnh này yêu cầu biên dịch module `com.example.api`.

Có thể chỉ định nhiều module, phân cách bằng dấu phẩy:

```bash
javac --module-source-path src -d out -m com.example.api,com.example.app
```

Khi chọn module ứng dụng, compiler cần giải quyết các module mà ứng dụng yêu cầu. Nếu dependency cũng được biên dịch từ source trong cùng module source path, hãy bảo đảm compiler có thể tìm thấy source của dependency và chọn tập module phù hợp với mục tiêu build.

Nếu dependency đã được biên dịch thành module output hoặc JAR, có thể đặt chúng trên `--module-path` thay vì biên dịch lại từ source trong cùng lượt.

## 7. Kết hợp với --module-path

Hai tùy chọn có vai trò khác nhau:

- `--module-source-path`: nơi tìm source code của các module đang biên dịch.
- `--module-path`: nơi tìm các module đã được biên dịch, chẳng hạn thư mục module output hoặc JAR.

Giả sử `com.example.api` đã được biên dịch thành module trong `libs/api-module`, còn source của app nằm trong `src/com.example.app`:

```text
project/
├── libs/
│   └── api-module/
│       └── com.example.api/
│           ├── module-info.class
│           └── com/example/api/Greeting.class
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
└── out/
```

Có thể biên dịch app với module path trỏ tới dependency đã có:

```bash
javac --module-path libs/api-module --module-source-path src -d out -m com.example.app
```

Compiler đọc source của app từ module source path và đọc module API đã biên dịch từ module path. Trong module descriptor của app vẫn cần:

```java
module com.example.app {
    requires com.example.api;
}
```

Không dùng `--module-source-path` thay cho `--module-path`: một bên phục vụ source module, bên còn lại phục vụ module đã biên dịch.

## 8. Khi nào dùng source path thông thường?

`-source-path` và `--module-source-path` phục vụ hai cách tổ chức source khác nhau:

| Tùy chọn | Mục đích |
| --- | --- |
| `-source-path` | Tìm source file theo package trong mô hình biên dịch thông thường. |
| `--module-source-path` | Tìm source tree của nhiều named module, có phân định module. |

Với dự án modular, mỗi module có `module-info.java` và source tree riêng, `--module-source-path` giúp compiler hiểu ranh giới module. Không nên gom source của nhiều module vào một package root rồi kỳ vọng compiler tự suy ra module ownership.

## 9. Lỗi thường gặp và cách xử lý

**Không tìm thấy module được chỉ định**

Ví dụ lỗi liên quan đến module không tồn tại hoặc không được tìm thấy trong module source path.

Kiểm tra:

- Tên module trong `-m` có khớp tên trong `module-info.java` không.
- Thư mục module có nằm đúng dưới module source path không.
- Pattern có trỏ tới đúng thư mục chứa `module-info.java` không.
- Tên thư mục và module name có bị sai chính tả hoặc khác chữ hoa/chữ thường không.

**Package không được export hoặc module không đọc được dependency**

Kiểm tra descriptor của dependency:

- Module tiêu thụ có `requires` module cung cấp package không.
- Module cung cấp package đã `exports` package cần dùng chưa.
- Dependency có nằm trên `--module-path` hoặc trong source tree được compiler tìm thấy không.

**Không tìm thấy class hoặc package**

Đối chiếu package declaration với cấu trúc thư mục source. Ví dụ `package com.example.app;` tương ứng với thư mục `com/example/app` bên trong source root của module.

**Output không có thư mục module như mong đợi**

Kiểm tra `-d` có trỏ đúng thư mục output không và module có được biên dịch như named module hay không. Với modular compilation, mỗi module có vùng output riêng dưới thư mục đích.

**Dùng nhầm --module-path và --module-source-path**

Xác định dependency đang ở dạng nào: file nguồn thì đặt trong module source path; module đã biên dịch hoặc modular JAR thì đặt trong module path.

## 10. Quy trình biên dịch thực tế

Với một dự án nhiều module nhỏ, có thể thực hiện theo trình tự:

1. Tạo source root, ví dụ `src/`.
2. Tạo thư mục riêng cho từng module, tên thư mục khớp module name.
3. Đặt `module-info.java` tại gốc source tree của từng module.
4. Viết package source bên trong thư mục module.
5. Khai báo `requires` và `exports` theo quan hệ module thực tế.
6. Chọn output directory bằng `-d`.
7. Dùng `--module-source-path` để chỉ vị trí source tree và `-m` để chọn module cần biên dịch.
8. Nếu có dependency đã biên dịch, thêm vị trí của chúng bằng `--module-path`.
9. Chạy ứng dụng bằng `java --module-path` và `--module`.

Lệnh mẫu cho cấu trúc ở phần 2:

```bash
javac --module-source-path src -d out -m com.example.api,com.example.app
java --module-path out -m com.example.app/com.example.app.Main
```

## 11. Ghi nhớ

- `--module-source-path` chỉ nơi chứa source tree của các named module.
- Tên thư mục module phải phù hợp với tên trong `module-info.java`.
- `-m` là dạng ngắn của `--module` trong javac, dùng để chỉ định module cần biên dịch.
- `-d` xác định nơi ghi output; output của các module được tách theo tên module.
- `--module-path` tìm module đã biên dịch, còn `--module-source-path` tìm module source.
- Khi chạy chương trình, dùng module path trỏ tới output và chỉ rõ module cùng main class.

Hãy bắt đầu từ cấu trúc thư mục và module descriptor. Khi hai phần này đúng, `javac --module-source-path` giúp biên dịch nhiều module từ một source tree có tổ chức và giữ nguyên ranh giới của Java Module System.
