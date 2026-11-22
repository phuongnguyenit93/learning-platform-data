# Descriptor mô-đun trong JAR đa phiên bản

JAR đa phiên bản (*multi-release JAR*, MR-JAR) có thể cung cấp nội dung khác nhau theo phiên bản Java đang chạy. Bên cạnh class và resource được đặt trong `META-INF/versions/<N>/`, JAR có thể chứa module descriptor tại `META-INF/versions/9/module-info.class`. Khi manifest bật `Multi-Release: true`, JDK trên module path nhận diện descriptor phiên bản 9 và sử dụng nó để xác định tên mô-đun, package được export cùng các chỉ thị JPMS khác.

Cách tổ chức này tách module metadata khỏi phần class ở thư mục gốc. Nó hữu ích khi một thư viện cần giữ cấu trúc JAR đa phiên bản nhưng vẫn muốn công bố một named module rõ ràng trên các JDK hiện hành.

## 1. Module descriptor trong MR-JAR là gì?

Module descriptor là file `module-info.class` được biên dịch từ `module-info.java`. Nó khai báo tên mô-đun, dependency và ranh giới truy cập, ví dụ `requires`, `exports`, `opens`, `uses` và `provides`.

Trong một MR-JAR, descriptor có thể được đặt ở:

```text
META-INF/versions/9/module-info.class
```

JAR cần khai báo thuộc tính sau trong phần main attributes của manifest:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Với cấu trúc này, `module-info.class` là một entry theo phiên bản. Nó không nằm ở root của JAR. Khi JDK tạo view của MR-JAR cho release 9 trở lên, descriptor phiên bản 9 được nhìn thấy và dùng làm metadata mô-đun.

## 2. Cấu trúc JAR sau khi đóng gói

Một MR-JAR chỉ có module descriptor theo phiên bản có thể có cấu trúc như sau:

```text
mr-greeter.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 9/
│           └── module-info.class
└── com/
    └── example/
        └── mr/
            └── Greeter.class
```

Manifest bật chế độ multi-release. Class `Greeter.class` nằm ở root; module descriptor nằm trong thư mục phiên bản 9. Descriptor mô tả package API mà JAR công bố khi được sử dụng như một named module.

Đừng nhầm hai việc: đặt file trong `META-INF/versions/9/` chỉ tạo entry theo phiên bản; manifest `Multi-Release: true` mới bật cách diễn giải multi-release của JAR. Thiếu thuộc tính này, runtime không áp dụng cơ chế chọn entry theo phiên bản như một MR-JAR.

## 3. Biên dịch module descriptor đúng phiên bản

Ví dụ thư viện cung cấp API `Greeter`:

**`src-lib/com/example/mr/Greeter.java`**

```java
package com.example.mr;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from the multi-release library";
    }
}
```

Module descriptor công bố package API:

**`module-src/module-info.java`**

```java
module com.example.mr {
    exports com.example.mr;
}
```

Biên dịch class thư viện và descriptor:

```powershell
New-Item -ItemType Directory -Force lib-base, lib-module, build | Out-Null
javac --release 17 -d lib-base src-lib/com/example/mr/Greeter.java
javac --release 9 -d lib-module module-src/module-info.java src-lib/com/example/mr/Greeter.java
```

`module-info.class` được biên dịch với `--release 9` vì nó sẽ nằm trong thư mục phiên bản `9`. Lệnh biên dịch descriptor cũng nhận source của package được export để compiler kiểm tra package đó tồn tại. Class thư viện ở root được biên dịch riêng theo baseline mà dự án đang hỗ trợ.

## 4. Tạo MR-JAR và thêm descriptor

Tạo manifest có thuộc tính `Multi-Release: true`:

**`MANIFEST.MF`**

```text
Manifest-Version: 1.0
Multi-Release: true

```

Đóng gói class thư viện ở root rồi thêm riêng `module-info.class` vào release 9:

```powershell
jar --create --file build/mr-greeter.jar --manifest MANIFEST.MF -C lib-base .
jar --update --file build/mr-greeter.jar --release 9 -C lib-module module-info.class
```

Trong lệnh thứ hai, `--release 9` khiến file theo sau được đặt dưới `META-INF/versions/9/`. Chỉ thêm `module-info.class` vào vùng phiên bản này; không đưa lại toàn bộ class thư viện nếu chúng đã nằm ở root và không cần một implementation thay thế theo phiên bản.

Kiểm tra nội dung archive:

```powershell
jar --list --file build/mr-greeter.jar
```

Kết quả cần có các entry chính:

```text
META-INF/MANIFEST.MF
com/example/mr/Greeter.class
META-INF/versions/9/module-info.class
```

Không nên có `module-info.class` ở root nếu mục tiêu là đặt descriptor trong vùng versioned. Module descriptor ở root và descriptor trong `META-INF/versions/9/` có ý nghĩa đóng gói khác nhau.

## 5. Kiểm tra descriptor theo release

Vì JAR không có root module descriptor, hãy chỉ định release khi dùng `jar --describe-module`:

```powershell
jar --describe-module --file build/mr-greeter.jar --release 9
jar --describe-module --file build/mr-greeter.jar --release 17
```

Trên JDK 24, cả hai lệnh trong ví dụ đều nhận diện module `com.example.mr` từ entry `META-INF/versions/9/module-info.class`:

```text
com.example.mr
exports com.example.mr
requires java.base mandated
```

JDK 24 cho biết descriptor được đọc từ đường dẫn versioned trong archive. Nếu chạy `jar --describe-module --file build/mr-greeter.jar` mà không có `--release`, công cụ có thể báo `No root module descriptor, specify --release`; điều này phù hợp với cấu trúc không đặt descriptor ở root.

Tiếp theo, xác nhận JAR đa phiên bản nhất quán:

```powershell
jar --validate --file build/mr-greeter.jar
```

`jar --validate` kiểm tra nội dung archive và tính nhất quán của API được export giữa các release khác nhau. Khi lệnh kết thúc thành công và không in lỗi, bước kiểm tra này không phát hiện vi phạm trong phạm vi nó kiểm tra.

## 6. Dùng MR-JAR như một named module

Consumer khai báo dependency theo tên trong module descriptor của thư viện:

**`app-src/com.example.consumer/module-info.java`**

```java
module com.example.consumer {
    requires com.example.mr;
}
```

**`app-src/com.example.consumer/com/example/consumer/Main.java`**

```java
package com.example.consumer;

import com.example.mr.Greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
```

Biên dịch consumer trên module path:

```powershell
New-Item -ItemType Directory -Force app-out | Out-Null
javac --release 17 --module-path build/mr-greeter.jar --module-source-path app-src -d app-out -m com.example.consumer
```

Chạy ứng dụng:

```powershell
java --module-path "build/mr-greeter.jar;app-out" -m com.example.consumer/com.example.consumer.Main
```

STDOUT:

```text
Hello from the multi-release library
```

Ví dụ này xác nhận JDK nhận diện descriptor versioned, consumer đọc được module `com.example.mr`, package được export và class trong JAR được nạp thành công.

## 7. Runtime chọn descriptor như thế nào?

JAR đa phiên bản tạo một view theo feature release của Java đang sử dụng. Entry versioned có phiên bản phù hợp được ưu tiên so với entry root. Trong ví dụ chỉ có descriptor tại release 9, vì vậy khi kiểm tra view release 9 hoặc 17 trên JDK 24, descriptor được chọn vẫn là `META-INF/versions/9/module-info.class`.

Module descriptor quyết định metadata JPMS của mô-đun trong view được chọn: tên module, dependency, package export/open và service use/provision. Các class và resource versioned khác vẫn được chọn theo cùng cơ chế MR-JAR. Descriptor không tự tạo class implementation; nó chỉ mô tả ranh giới và quan hệ mô-đun.

Khi ứng dụng chạy trên module path, JDK dùng descriptor phù hợp để resolve module graph và kiểm soát khả năng đọc/truy cập package. Khi JAR được đặt trên classpath, ứng dụng chạy trong unnamed module; descriptor không làm cho ứng dụng classpath trở thành named module.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Consumer báo `module not found` | JAR không nằm trên module path, tên trong `requires` sai hoặc descriptor không được nhận diện. | Kiểm tra manifest, đường dẫn versioned và `jar --describe-module --release 9`. |
| `jar --describe-module` yêu cầu chỉ định release | JAR không có descriptor ở root, descriptor chỉ nằm trong thư mục versioned. | Dùng `--release 9` hoặc release mục tiêu cần kiểm tra. |
| JAR bị coi như automatic module | `Multi-Release: true` thiếu/sai trong main attributes hoặc descriptor versioned không đúng vị trí. | Kiểm tra manifest và xác nhận entry `META-INF/versions/9/module-info.class`. |
| `package ... is not visible` | Descriptor không export package mà consumer cần. | Bổ sung `exports` có chủ đích vào module descriptor và build lại. |
| `jar --validate` báo API không nhất quán | Các release cung cấp API được export khác nhau theo cách công cụ xác định là không nhất quán. | Kiểm tra class versioned, package export và descriptor; duy trì hợp đồng API tương thích. |
| Descriptor không compile | Package export không có trong source/module compilation hoặc descriptor được biên dịch sai release. | Biên dịch `module-info.java` cùng source của package và dùng `--release` khớp version directory. |

Không xử lý lỗi bằng cách thêm mọi package vào `exports`. Chỉ công bố package thuộc API được hỗ trợ và kiểm tra descriptor sau khi đóng gói.

## 9. Checklist phát hành

1. Đặt `Multi-Release: true` trong main attributes của manifest.
2. Đặt descriptor tại `META-INF/versions/9/module-info.class` và biên dịch nó với `javac --release 9`.
3. Giữ class/resource ở root hoặc versioned directory theo baseline và yêu cầu thực tế của thư viện.
4. Dùng `jar --list` xác nhận đường dẫn descriptor; bảo đảm không vô tình thêm descriptor ở root.
5. Dùng `jar --describe-module --release 9` và release mục tiêu để xác nhận tên module, exports và requires.
6. Chạy `jar --validate` để kiểm tra tính nhất quán của API được export.
7. Biên dịch một named consumer với `--module-path` và chạy bằng module path chứa MR-JAR.
8. Kiểm tra manifest và module descriptor của chính artifact cuối cùng trong pipeline phát hành.

Đặt module descriptor trong `META-INF/versions/9/` cho phép MR-JAR công bố ranh giới JPMS mà vẫn giữ descriptor như một entry theo phiên bản. Manifest `Multi-Release: true`, descriptor được biên dịch đúng release và kiểm tra bằng `jar --describe-module`/`jar --validate` là các điều kiện cần xác nhận trước khi dùng JAR như một named module.