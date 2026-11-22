# javac -d tạo output theo module

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của tùy chọn `javac -d` khi biên dịch Java.
- Đọc cấu trúc source tree của một modular project.
- Dùng `--module-source-path` và `-m` để biên dịch một hoặc nhiều module.
- Xác định chính xác vị trí của `module-info.class` và các file `.class` sau khi biên dịch.
- Phân biệt cách biên dịch theo module source path với cách truyền trực tiếp source file của từng module.
- Dùng output directory làm module path cho bước chạy ứng dụng.

## 1. Vai trò của javac -d

`javac` là Java compiler. Khi biên dịch source code, compiler cần một nơi để ghi các file đầu ra, chủ yếu là bytecode `.class` và descriptor đã biên dịch `module-info.class`.

Tùy chọn:

~~~bash
javac -d <output-directory> <source-files>
~~~

Trong đó:

- `-d` là viết tắt của `--directory`.
- `<output-directory>` là thư mục gốc để compiler ghi kết quả.
- Compiler tự tạo các thư mục con cần thiết theo cấu trúc package và cách source/module được đưa vào lệnh.
- Nếu không chỉ định `-d`, javac ghi class file cạnh source file tương ứng.

Điểm cần nhớ: `-d` xác định thư mục đích. Nó không tự suy ra mọi module trong project rồi luôn tạo thư mục con theo tên module. Cách chia output theo từng module phụ thuộc vào cách bạn cung cấp module source, đặc biệt là `--module-source-path`, hoặc việc bạn chủ động chọn output directory riêng cho từng module.

## 2. Source tree của một modular project

Giả sử ứng dụng có hai module:

- `com.acme.common`: cung cấp API dùng chung.
- `com.acme.app`: ứng dụng chính và phụ thuộc vào `com.acme.common`.

Cấu trúc source:

~~~text
project/
└── src/
    ├── com.acme.common/
    │   ├── module-info.java
    │   └── com/
    │       └── acme/
    │           └── common/
    │               └── Version.java
    └── com.acme.app/
        ├── module-info.java
        └── com/
            └── acme/
                └── app/
                    └── Main.java
~~~

Mỗi thư mục ngay dưới `src/` là một module source root. Tên thư mục module khớp với tên module khai báo trong `module-info.java`.

Ví dụ descriptor của module common:

~~~java
module com.acme.common {
    exports com.acme.common;
}
~~~

Class được export:

~~~java
package com.acme.common;

public final class Version {
    private Version() {
    }

    public static String value() {
        return "1.0";
    }
}
~~~

Descriptor của module ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.common;
}
~~~

Class main:

~~~java
package com.acme.app;

import com.acme.common.Version;

public class Main {
    public static void main(String[] args) {
        System.out.println("Common version: " + Version.value());
    }
}
~~~

Mỗi module có descriptor riêng. `module-info.java` là source descriptor; sau khi biên dịch, compiler tạo `module-info.class` trong output của chính module đó.

## 3. Biên dịch nhiều module bằng --module-source-path

Khi source tree đã được tổ chức theo module, bạn có thể yêu cầu javac tìm module source bằng `--module-source-path`.

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
~~~

Ý nghĩa từng phần:

| Thành phần | Vai trò |
|---|---|
| `javac` | Khởi chạy Java compiler |
| `-d out` | Chọn `out/` làm output root |
| `--module-source-path src` | Cho compiler biết nơi chứa source tree của các module |
| `-m com.acme.common,com.acme.app` | Chỉ định các module cần biên dịch |

Trong ví dụ này, `-d out` kết hợp với module source path khiến compiler tạo một thư mục output cho từng module. Kết quả có dạng:

~~~text
project/
├── src/
│   ├── com.acme.common/
│   │   ├── module-info.java
│   │   └── com/acme/common/Version.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── out/
    ├── com.acme.common/
    │   ├── module-info.class
    │   └── com/acme/common/
    │       └── Version.class
    └── com.acme.app/
        ├── module-info.class
        └── com/acme/app/
            └── Main.class
~~~

Có thể đọc cấu trúc output theo quy tắc:

~~~text
<output-root>/
    <module-name>/
        module-info.class
        <package-path>/
            <ClassName>.class
~~~

Ví dụ:

- `out/com.acme.common/module-info.class` là descriptor đã biên dịch của common.
- `out/com.acme.common/com/acme/common/Version.class` là bytecode của class Version.
- `out/com.acme.app/module-info.class` là descriptor đã biên dịch của app.
- `out/com.acme.app/com/acme/app/Main.class` là bytecode của class Main.

Như vậy, output root `out/` có thể được dùng như một module path chứa nhiều exploded module. Mỗi thư mục con tương ứng với một module đã biên dịch.

## 4. Chạy ứng dụng từ output directory

Sau khi biên dịch thành công, có thể dùng output root làm module path:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Trong đó:

- `--module-path out` cho JVM biết nơi tìm các module đã biên dịch.
- `-m com.acme.app/com.acme.app.Main` chọn module `com.acme.app` và main class `com.acme.app.Main`.

Kết quả:

~~~text
Common version: 1.0
~~~

JVM tìm module app trong `out/`, đọc descriptor để biết app yêu cầu module common, rồi resolve module graph. Cả hai module đều có trong module path nên ứng dụng có thể chạy.

Luồng làm việc:

~~~text
src/
  com.acme.common/
  com.acme.app/
        |
        | javac -d out
        | --module-source-path src
        | -m com.acme.common,com.acme.app
        v
out/
  com.acme.common/
  com.acme.app/
        |
        | java --module-path out
        | -m com.acme.app/com.acme.app.Main
        v
     Application
~~~

## 5. Biên dịch từng module với output directory riêng

Không bắt buộc phải dùng `--module-source-path`. Bạn cũng có thể truyền trực tiếp source file và chọn output directory riêng cho từng module.

Ví dụ, biên dịch common trước:

~~~bash
javac -d mods/com.acme.common ^
    src/com.acme.common/module-info.java ^
    src/com.acme.common/com/acme/common/Version.java
~~~

Sau đó biên dịch app, sử dụng output root `mods/` làm module path để compiler tìm common:

~~~bash
javac --module-path mods ^
    -d mods/com.acme.app ^
    src/com.acme.app/module-info.java ^
    src/com.acme.app/com/acme/app/Main.java
~~~

Ví dụ trên dùng ký hiệu xuống dòng của Windows Command Prompt. Trong PowerShell hoặc terminal khác, có thể viết mỗi lệnh trên một dòng hoặc dùng ký hiệu nối dòng phù hợp với shell.

Cấu trúc output cuối cùng:

~~~text
mods/
├── com.acme.common/
│   ├── module-info.class
│   └── com/acme/common/Version.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Ở cách này, compiler không cần tự tạo thư mục con theo tên module từ một module source path. Chính lệnh build chọn `mods/com.acme.common` và `mods/com.acme.app` làm output directory tương ứng.

Có thể chạy ứng dụng bằng cùng module path:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Hai cách tổ chức trên có cùng mục tiêu: mỗi exploded module có một thư mục gốc chứa `module-info.class` và package tree của module.

## 6. Phân biệt -d, --module-source-path và -m

Ba tùy chọn này có trách nhiệm khác nhau:

| Tùy chọn | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `-d` | Ghi output vào đâu? | `-d out` |
| `--module-source-path` | Tìm source của các module ở đâu và theo cấu trúc nào? | `--module-source-path src` |
| `-m` / `--module` | Biên dịch module nào? | `-m com.acme.common,com.acme.app` |

Không nên nhầm `-d` với `--module-source-path`:

- `-d` điều khiển output.
- `--module-source-path` mô tả vị trí và cấu trúc source module.
- `-m` chọn module cần biên dịch trong module source path.

Ví dụ chỉ có `-d out`:

~~~bash
javac -d out src/com/acme/app/Main.java
~~~

Đây là lệnh biên dịch source file thông thường. Compiler giữ cấu trúc package dưới output root, chẳng hạn `out/com/acme/app/Main.class`. Không có thông tin module source path để javac tự tổ chức nhiều module thành `out/<module-name>/...`.

Ví dụ có module source path:

~~~bash
javac -d out --module-source-path src -m com.acme.app
~~~

Lệnh này sử dụng cấu trúc source module để tạo output theo module. Khi có nhiều module, mỗi module được đặt trong thư mục con tương ứng dưới output root.

## 7. Output directory và module path

Một exploded module là một thư mục chứa descriptor đã biên dịch và nội dung module. Ví dụ:

~~~text
mods/
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Khi dùng `--module-path mods`, module path có thể chứa:

- Thư mục trực tiếp của một exploded module.
- Thư mục gốc chứa nhiều exploded module.
- Modular JAR.
- Các vị trí module hợp lệ khác được Java module system hỗ trợ.

Với output root chứa nhiều module như `out/` hoặc `mods/`, JVM quét các module con theo cấu trúc module path. Bạn không cần truyền riêng từng thư mục module trong lệnh chạy.

Điều này làm cho output của javac trở thành đầu vào trực tiếp của bước chạy:

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Trong quy trình phát hành, các exploded module cũng có thể được đóng gói thành modular JAR. Việc đóng gói là bước riêng; `javac -d` chỉ tạo output directory và bytecode.

## 8. Những điều cần kiểm tra khi output không đúng

### Module output bị đặt sai vị trí

Kiểm tra:

- Source tree có theo cấu trúc module source path không?
- Tên thư mục module có khớp tên khai báo trong `module-info.java` không?
- Lệnh có `--module-source-path` khi muốn compiler tự tổ chức output theo module không?
- `-d` có trỏ đến output root dự kiến không?

### Không tìm thấy dependency module

Nếu module app có:

~~~java
module com.acme.app {
    requires com.acme.common;
}
~~~

thì module common phải có trong một finder mà compiler có thể truy cập, chẳng hạn module source path hoặc module path đã biên dịch.

Khi biên dịch app riêng sau khi common đã được biên dịch:

~~~bash
javac --module-path mods -d mods/com.acme.app <app-source-files>
~~~

Kiểm tra `mods/com.acme.common/module-info.class` tồn tại và module path trỏ đúng đến `mods/`.

### Không tìm thấy main class khi chạy

Kiểm tra:

- Output của module app có `module-info.class` và package tree không?
- Tên module sau `-m` có đúng với descriptor không?
- Tên main class có đầy đủ package không?
- Module path có trỏ đến thư mục cha chứa các module không?

### Class cũ vẫn còn trong output

Javac ghi đè class file tương ứng khi biên dịch lại, nhưng không nên giả định nó sẽ tự xóa mọi class cũ không còn source tương ứng. Nếu xóa hoặc đổi tên class/package, output cũ có thể giữ lại bytecode không còn thuộc source hiện tại.

Với build có tính tái lập, hãy để Gradle/Maven hoặc script build xóa output directory trước khi biên dịch lại. Ví dụ:

~~~bash
rm -rf out
javac -d out --module-source-path src -m com.acme.common,com.acme.app
~~~

Trên Windows PowerShell, có thể dùng `Remove-Item -Recurse -Force out` trước khi chạy lệnh javac. Chỉ xóa đúng thư mục output do build quản lý.

### Không thấy module-info.class

Module source cần có `module-info.java` ở module root. Nếu project được biên dịch như classpath project thông thường hoặc source descriptor không được đưa vào lần biên dịch, output có thể không có `module-info.class` như mong muốn.

## 9. Quy trình mẫu từ source đến runtime

Với project hai module ở phần trước, quy trình cơ bản là:

1. Tạo source root riêng cho từng module.
2. Viết `module-info.java` để khai báo tên module, dependency và package được export.
3. Dùng `javac -d out --module-source-path src -m ...` để biên dịch các module.
4. Kiểm tra output có thư mục riêng cho từng module, mỗi thư mục có `module-info.class`.
5. Dùng `java --module-path out -m module/main-class` để chạy.
6. Khi source thay đổi cấu trúc, làm sạch output directory rồi biên dịch lại.

Bộ lệnh minh họa:

~~~bash
javac -d out --module-source-path src -m com.acme.common,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Khi đã hiểu cấu trúc output, bạn có thể kiểm tra nhanh một bản build bằng cách mở thư mục output và xác nhận:

- Có đúng một thư mục cho mỗi module được biên dịch.
- Mỗi module có `module-info.class`.
- Package path trong output khớp package khai báo trong source.
- Các dependency module có mặt trên module path khi compile và runtime.

## Kết luận

`javac -d` chỉ định thư mục gốc để ghi kết quả biên dịch. Khi kết hợp với `--module-source-path` và `-m`, javac tổ chức output thành các thư mục riêng theo tên module, bên trong mỗi thư mục có `module-info.class` và cây package chứa bytecode. Nếu truyền source file trực tiếp, bạn có thể chọn một output directory riêng cho từng module.

Hãy ghi nhớ ba vai trò: **`-d` chọn nơi ghi, `--module-source-path` mô tả nơi tìm source module, và `-m` chọn module cần biên dịch.** Output root sau đó có thể được dùng làm module path cho JVM.
