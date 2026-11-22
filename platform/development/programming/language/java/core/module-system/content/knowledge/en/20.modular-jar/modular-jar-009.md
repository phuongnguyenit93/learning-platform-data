# Đảm bảo JAR phát hành không chứa split package

## 1. Split package là gì?

Trong Java, **package** là không gian tên chứa các class và interface. Một **split package** xảy ra khi cùng một package name xuất hiện trong nhiều module/JAR độc lập.

Ví dụ hai JAR:

```text
dist/
├── acme-core.jar
└── acme-plugin.jar
```

Cả hai đều chứa class trong package `com.acme.util`:

```text
acme-core.jar
└── com/acme/util/StringHelper.class

acme-plugin.jar
└── com/acme/util/DateHelper.class
```

Khi hai JAR trở thành hai named module trên module path, package `com.acme.util` bị chia giữa hai module. Đây là cấu trúc cần tránh khi phát hành ứng dụng theo JPMS.

Quy tắc thiết kế an toàn là **mỗi package thuộc về đúng một named module** trong tập module được phát hành và chạy cùng nhau. Package ownership rõ ràng giúp module graph nhất quán, tránh xung đột khi resolve và giữ ranh giới truy cập package-private đúng như thiết kế.

## 2. Vì sao split package gây vấn đề?

### Xung đột khi resolve module

JPMS kiểm tra tính nhất quán của module graph. Nếu một module đọc hai module khác nhau cùng export một package, resolver không thể xác định duy nhất nguồn package đó và resolution có thể thất bại với `ResolutionException`.

Ví dụ:

```text
com.acme.app
   | requires
   +------> com.acme.core  -- exports com.acme.util
   |
   +------> com.acme.plugin -- exports com.acme.util
```

Ứng dụng đọc cả hai module và cả hai đều export `com.acme.util`. Đây là split-package conflict trong graph.

Không nên dựa vào việc một package trùng tên tình cờ chưa gây lỗi trong một cấu hình cụ thể. Khi dependency graph thay đổi, một module mới có thể đọc cả hai nguồn package và làm resolution thất bại.

### Package-private không chia sẻ giữa hai module

Hai class cùng khai báo `package com.acme.util` nhưng nằm trong hai named module khác nhau không vì thế mà trở thành cùng một runtime package. Các class không thể dựa vào package-private access để gọi lẫn nhau như khi chúng nằm trong cùng module/package.

Điều này có thể làm hỏng giả định cũ của ứng dụng chạy trên classpath, nơi nhiều JAR cùng đóng góp class vào một package.

### Tăng rủi ro khi thay đổi dependency và đóng gói

Split package khiến việc nâng cấp hoặc thay thế một JAR dễ gây xung đột. Nó cũng làm khó việc xác định module nào sở hữu API, class hoặc resource của package. Với automatic modules, các package được export rộng rãi nên các xung đột package trong graph có thể lộ ra khi chuyển từ classpath sang module path.

## 3. Nhận diện split package trong các JAR phát hành

Kiểm tra **toàn bộ tập JAR được triển khai cùng nhau**, không chỉ kiểm tra từng JAR riêng lẻ. Một JAR không tự chứa package trùng bên trong vẫn có thể xung đột với JAR khác.

Ví dụ liệt kê nội dung JAR:

```bash
jar --list --file dist/acme-core.jar
jar --list --file dist/acme-plugin.jar
```

Tìm các đường dẫn class có cùng thư mục package, chẳng hạn:

```text
com/acme/util/StringHelper.class
com/acme/util/DateHelper.class
```

Xem module descriptor và các package được công bố:

```bash
jar --describe-module --file dist/acme-core.jar
jar --describe-module --file dist/acme-plugin.jar
```

Lệnh này giúp xác nhận tên module, module descriptor và thông tin package. Với automatic module, tên module được suy ra từ tên JAR và package export có quy tắc khác explicit module; vẫn phải kiểm tra package overlap trong toàn bộ tập module.

## 4. Kiểm tra module graph bằng Java launcher

Có thể yêu cầu Java validate các module trên module path:

```bash
java --validate-modules \
  --module-path dist \
  --add-modules ALL-MODULE-PATH
```

`ALL-MODULE-PATH` yêu cầu đưa các module quan sát được trên module path vào phạm vi kiểm tra. Nếu graph có xung đột hoặc module không hợp lệ, lệnh có thể báo lỗi thay vì kết thúc thành công.

Đây là bước kiểm tra module graph tổng thể. Lỗi có thể liên quan tới dependency hoặc cấu hình module khác, không chỉ split package; hãy đọc đầy đủ thông báo lỗi để xác định hai module và package liên quan.

Có thể kiểm tra dependency và descriptor của một module cụ thể bằng `jdeps`:

```bash
jdeps --check com.acme.app --module-path dist
```

`jdeps --check` hỗ trợ xem xét module descriptor và dependency của module được chỉ định. Dùng nó cùng với module validation và kiểm tra package inventory để có kết quả rõ ràng.

## 5. Tự động quét package trùng giữa các JAR

Để chặn lỗi ngay trong build/release pipeline, có thể tạo một package inventory từ tất cả JAR trong thư mục phát hành rồi tìm package xuất hiện ở nhiều artifact.

Script Python dưới đây dùng thư viện chuẩn `zipfile`, không cần cài package bên ngoài. Nó nhận một thư mục phát hành, quét đệ quy các file `.jar`, bỏ qua `module-info.class` và chuẩn hóa đường dẫn class trong multi-release JAR trước khi xác định package.

Lưu thành `check_split_packages.py`:

```python
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
import sys

if len(sys.argv) != 2:
    print("Usage: python check_split_packages.py <release-directory>")
    raise SystemExit(2)

root = Path(sys.argv[1])
if not root.is_dir():
    print(f"Not a directory: {root}")
    raise SystemExit(2)

owners = defaultdict(set)
jar_count = 0

for jar_path in sorted(root.rglob("*.jar")):
    jar_count += 1
    try:
        with ZipFile(jar_path) as jar:
            for entry in jar.namelist():
                name = entry.replace("\\", "/")

                # Multi-release classes live below META-INF/versions/<N>/.
                if name.startswith("META-INF/versions/"):
                    parts = name.split("/", 3)
                    if len(parts) != 4:
                        continue
                    name = parts[3]
                elif name.startswith("META-INF/"):
                    continue

                if not name.endswith(".class"):
                    continue
                if name.rsplit("/", 1)[-1] == "module-info.class":
                    continue

                package_path = name.rpartition("/")[0]
                package_name = (
                    package_path.replace("/", ".")
                    if package_path
                    else "<default package>"
                )
                owners[package_name].add(jar_path.relative_to(root).as_posix())

    except Exception as error:
        print(f"Cannot read {jar_path}: {error}")
        raise SystemExit(2)

duplicates = {
    package: sorted(paths)
    for package, paths in owners.items()
    if len(paths) > 1
}

print(f"Scanned {jar_count} JAR file(s) under {root}")

if duplicates:
    print("Split packages found:")
    for package, paths in sorted(duplicates.items()):
        print(f"  {package}")
        for path in paths:
            print(f"    - {path}")
    raise SystemExit(1)

print("No package appears in more than one JAR.")
```

Chạy script từ thư mục project:

```bash
python check_split_packages.py dist
```

Kết quả khi có lỗi:

```text
Scanned 3 JAR file(s) under dist
Split packages found:
  com.acme.util
    - acme-core.jar
    - acme-plugin.jar
```

Kết quả khi không có package trùng:

```text
Scanned 3 JAR file(s) under dist
No package appears in more than one JAR.
```

Script kiểm tra package được suy ra từ đường dẫn các file class. Nó là một hàng rào kiểm tra hữu ích cho artifact, nhưng không thay thế việc validate module graph bằng JDK. Nếu một JAR lỗi định dạng hoặc không đọc được, script kết thúc với mã lỗi khác 0 để pipeline không bỏ qua artifact đó.

## 6. Tích hợp kiểm tra vào quy trình phát hành

Một quy trình đơn giản có thể đặt các bước sau sau khi build tất cả JAR:

1. Tạo thư mục staging chỉ chứa các artifact sẽ phát hành cùng nhau.
2. Chạy package inventory để phát hiện package xuất hiện trong nhiều JAR.
3. Chạy `java --validate-modules` trên module path staging.
4. Chạy `jdeps --check` cho các module ứng dụng quan trọng.
5. Chạy integration test trên module path, không chỉ trên classpath.
6. Chỉ đóng gói hoặc publish artifact khi tất cả kiểm tra bắt buộc thành công.

Ví dụ pipeline ở mức lệnh:

```bash
python check_split_packages.py dist

java --validate-modules \
  --module-path dist \
  --add-modules ALL-MODULE-PATH

jdeps --check com.acme.app --module-path dist
```

Trong CI, cần cấu hình các lệnh này làm bước bắt buộc. Nếu script tìm thấy package trùng hoặc Java validation trả về lỗi, build phải thất bại để artifact không được phát hành.

Nên chạy kiểm tra trên đúng thư mục staging cuối cùng. Kiểm tra source set hoặc thư mục build trung gian có thể bỏ sót JAR được đóng gói từ dependency bên ngoài hoặc artifact được copy thêm ở bước release.

## 7. Cách xử lý khi phát hiện split package

Khi hai JAR cùng chứa package, trước tiên xác định package đó thuộc về module nào theo thiết kế.

- **Chuyển class về một module sở hữu package:** nếu các class cùng thuộc một thành phần, gom chúng vào một module và chỉ phát hành package từ module đó.
- **Tách package theo trách nhiệm:** nếu hai nhóm class có mục đích khác nhau, đổi package của một nhóm, ví dụ `com.acme.core.util` và `com.acme.plugin.util`.
- **Điều chỉnh ranh giới module:** nếu hai module cần chia sẻ implementation nội bộ chặt chẽ, cân nhắc gộp chúng hoặc thiết kế lại API giữa module.
- **Kiểm tra dependency đóng gói:** một thư viện bên thứ ba có thể mang package trùng vào distribution. Cần nâng phiên bản, loại trừ artifact xung đột hoặc chọn cách đóng gói phù hợp với giấy phép và runtime.

Không nên chỉ đổi tên module trong `module-info.java`: tên module khác nhau không giải quyết được việc hai module vẫn chứa cùng package. Cũng không nên dùng `--patch-module` như cách sửa mặc định cho artifact phát hành; đây là cơ chế đặc biệt để bổ sung nội dung vào một module đã chọn và cần được dùng có chủ đích.

## 8. Những trường hợp cần lưu ý

- **Classpath và module path:** ứng dụng cũ có thể chạy khi nhiều JAR cùng đóng góp class vào một package trên classpath. Khi chuyển các JAR thành named hoặc automatic modules, module graph áp dụng các ràng buộc khác.
- **Automatic modules:** tên module được suy ra từ tên JAR nếu không có descriptor. Chúng vẫn tham gia module graph và có thể tạo xung đột package.
- **Multi-release JAR:** class có thể nằm trong `META-INF/versions/<version>/`. Công cụ kiểm tra cần tính cả các package trong các phiên bản class này.
- **Package-private:** cùng package name không đồng nghĩa cùng runtime package nếu class thuộc các module khác nhau.
- **Package trùng nhưng không cùng được đọc:** một số graph cụ thể có thể chưa phát sinh xung đột resolution nếu không có module nào đọc đồng thời các nguồn export trùng. Tuy nhiên, phát hành package ownership không rõ ràng vẫn làm hệ thống mong manh khi graph thay đổi.

## Ghi nhớ

- Split package là cùng một package name được chia giữa nhiều module/JAR.
- Trong module graph, hai module export cùng package tới một module đọc cả hai có thể khiến resolution thất bại.
- Áp dụng quy tắc một package có một module sở hữu trong distribution.
- Quét tất cả JAR phát hành cùng nhau; kiểm tra từng JAR riêng lẻ là chưa đủ.
- Dùng package inventory, `java --validate-modules`, `jdeps --check` và integration test trên module path.
- Sửa tận gốc bằng cách gom class vào một module hoặc tách package theo trách nhiệm; đổi tên module không sửa được split package.
