# Split package giữa module path và classpath

## 1. Split package là gì?

Một **split package** xảy ra khi cùng một tên package được chứa trong nhiều đơn vị triển khai độc lập, chẳng hạn nhiều JAR. Ví dụ:

```text
lib-core.jar
└── com/acme/util/StringHelper.class

lib-extra.jar
└── com/acme/util/DateHelper.class
```

Cả hai JAR đều đóng góp class vào package `com.acme.util`. Cách Java xử lý cấu trúc này phụ thuộc vào nơi đặt JAR:

- Trên **classpath**, các class thường thuộc unnamed module của class loader. Nhiều JAR trên classpath có thể cùng đóng góp class vào một package.
- Trên **module path**, mỗi explicit module hoặc automatic module có ranh giới riêng. Package được gắn với module sở hữu nó; việc cùng package xuất hiện trong nhiều named module có thể làm module resolution thất bại khi một module đọc đồng thời các nguồn package đó.

Vì vậy, một cấu trúc chạy được trên classpath có thể không chạy được sau khi chuyển các JAR lên module path. Đây là vấn đề thường gặp khi modular hóa một ứng dụng Java cũ.

## 2. Classpath: nhiều JAR cùng đóng góp vào unnamed module

Khi khởi chạy bằng `-cp` hoặc `--class-path`, các thư mục và JAR được chỉ định được tìm kiếm bởi class loader. Với class loader ứng dụng thông thường, các class trên classpath thuộc unnamed module tương ứng.

Ví dụ:

```text
app.jar
lib-core.jar
lib-extra.jar
```

Chạy:

```bash
java -cp "app.jar:lib-core.jar:lib-extra.jar" com.acme.app.Main
```

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

```powershell
java -cp "app.jar;lib-core.jar;lib-extra.jar" com.acme.app.Main
```

Nếu `lib-core.jar` và `lib-extra.jar` chứa các class khác nhau nhưng cùng package `com.acme.util`, ứng dụng thường vẫn có thể nạp cả hai. Package không bị chia thành hai named module; các class được nạp vào cùng unnamed module của class loader đó.

Đây là lý do nhiều thư viện Java cũ có thể chia package qua nhiều JAR mà vẫn hoạt động trên classpath.

Tuy nhiên, classpath không làm mọi xung đột biến mất:

- Nếu hai JAR chứa cùng binary class name, ví dụ cả hai đều có `com.acme.util.StringHelper`, class loader thường nạp bản tìm thấy đầu tiên theo thứ tự tìm kiếm (sau cơ chế delegation của loader).
- Thứ tự classpath có thể ảnh hưởng kết quả và khiến lỗi chỉ xuất hiện ở một môi trường triển khai.
- Nếu các class được nạp bởi class loader khác nhau, chúng không tự động thuộc cùng runtime package; package-private access có thể thất bại.

Classpath chấp nhận việc nhiều JAR đóng góp class vào package, nhưng không bảo đảm các class trùng tên hoặc các class loader khác nhau tương thích.

## 3. Module path: package thuộc về module

Khi JAR được đặt trên module path, Java xác định module từ:

- `module-info.class` của explicit named module; hoặc
- Quy tắc suy ra tên và nội dung của automatic module nếu JAR không có descriptor phù hợp.

Module descriptor xác định các package được module sở hữu và những package được export. Các module không còn đơn thuần là những JAR cùng đổ class vào một classpath chung.

Ví dụ:

```text
com.acme.core
└── exports com.acme.util

com.acme.extra
└── exports com.acme.util

com.acme.app
├── requires com.acme.core
└── requires com.acme.extra
```

Nếu cả `com.acme.core` và `com.acme.extra` export package `com.acme.util` tới `com.acme.app`, module system không thể chọn một nguồn package duy nhất cho consumer. Resolution có thể thất bại với `ResolutionException`, kèm thông báo rằng hai module export cùng package tới một module.

Không nên thiết kế dựa trên việc split package tình cờ chưa gây lỗi trong một graph cụ thể. Khi thêm dependency hoặc thay đổi module đọc các package đó, xung đột có thể xuất hiện.

Với named module, cùng package name không có nghĩa các class thuộc cùng một module hoặc được chia sẻ quyền truy cập package-private. Package ownership là một phần của ranh giới module.

## 4. Vì sao classpath và module path cho kết quả khác nhau?

So sánh:

| Nội dung | Classpath | Module path |
|---|---|---|
| Đơn vị tổ chức | Các entry được tìm bởi class loader | Explicit hoặc automatic module |
| Module chứa class | Thường là unnamed module của loader | Named module |
| Nhiều JAR cùng package | Thường có thể cùng đóng góp vào package của unnamed module | Có thể gây split-package conflict trong module graph |
| Package visibility | Quy tắc truy cập Java truyền thống trong runtime package | Kết hợp quy tắc truy cập Java và exports/opens của module |
| Dependency declaration | Không có `requires` trong module descriptor | Có `requires`, `exports`, `uses`, `provides` |
| Module resolution | Không resolve graph cho các classpath JAR | Resolve root modules và dependency |
| Class trùng binary name | Thứ tự tìm kiếm/class loader có thể quyết định class được nạp | Module ownership và resolution phải nhất quán; không nên có hai nguồn package cạnh tranh |

Trên classpath, các JAR được nhìn như các nguồn class của unnamed module. Trên module path, mỗi module là một đơn vị độc lập với package ownership và dependency rõ ràng. Vì vậy, chỉ đổi tham số khởi chạy từ `-cp` sang `--module-path` không phải là một bước modular hóa đầy đủ.

## 5. Split package khi trộn classpath và module path

Một ứng dụng có thể đồng thời dùng cả classpath và module path:

```bash
java --module-path mods \
  --class-path legacy-libs/* \
  -m com.acme.app/com.acme.app.Main
```

Trong cấu hình này:

- Các module trong `mods` là named hoặc automatic modules.
- Các thư viện trong `legacy-libs` thuộc unnamed module của class loader tương ứng.
- Package cùng tên ở hai phía vẫn nằm trong các module/loading context khác nhau; chúng không tự động hợp nhất thành một package dùng chung.

Một điểm quan trọng là named module không đọc unnamed module theo mặc định. Vì vậy, nếu `com.acme.app` là named module và cần một thư viện vẫn để trên classpath, khai báo `requires` tới tên JAR đó sẽ không biến thư viện classpath thành một named module.

Ngược lại, code chạy trong unnamed module có thể đọc các named module được đưa vào module layer phù hợp. Sự bất đối xứng này làm cho quá trình chuyển đổi từng phần cần được thiết kế cẩn thận.

Nếu cùng package xuất hiện trên cả module path và classpath, hãy kiểm tra module nào thực sự sở hữu từng class và class loader nào nạp chúng. Đừng dựa vào việc hai tên package giống nhau để giả định package-private access, class identity hoặc thứ tự nạp sẽ giống như khi tất cả JAR nằm trên classpath.

Các biểu hiện khi trộn không đúng có thể gồm package không visible lúc compile, class không tìm thấy ở runtime, lỗi truy cập hoặc liên kết nhầm phiên bản class. Nguyên nhân cụ thể phụ thuộc vào module graph, class loader và cách ứng dụng được biên dịch/khởi chạy.

## 6. Ví dụ chuyển hai JAR từ classpath sang module path

Giả sử ban đầu có:

```text
legacy-app.jar
legacy-core.jar
legacy-extra.jar
```

Hai thư viện chứa:

```text
legacy-core.jar
└── com/acme/util/StringHelper.class

legacy-extra.jar
└── com/acme/util/DateHelper.class
```

Cách chạy cũ:

```bash
java -cp "legacy-app.jar:legacy-core.jar:legacy-extra.jar" \
  com.acme.app.Main
```

Cấu trúc này có thể hoạt động vì các class cùng package được nạp trong unnamed module.

Nếu chuyển cả hai thư viện thành hai automatic module trên module path, package `com.acme.util` được xuất hiện trong hai module riêng. Automatic module có quy tắc export package rộng, nên xung đột package có thể lộ ra trong quá trình resolution khi consumer đọc cả hai.

Nếu chuyển `legacy-core.jar` lên module path nhưng để `legacy-extra.jar` trên classpath, hai phần package nằm trong named module và unnamed module. Named module không tự đọc phần classpath còn lại. Một dependency vốn chạy được trên classpath vì vậy có thể không còn hoạt động.

Cách sửa bền vững là xác định package thuộc module nào và tổ chức artifact theo ranh giới đó, thay vì chỉ đổi vị trí JAR.

## 7. Cách kiểm tra package trong từng JAR

Liệt kê class trong JAR:

```bash
jar --list --file legacy-core.jar
jar --list --file legacy-extra.jar
```

Tìm các đường dẫn có cùng thư mục package, ví dụ:

```text
com/acme/util/StringHelper.class
com/acme/util/DateHelper.class
```

Xem module descriptor hoặc tên automatic module:

```bash
jar --describe-module --file legacy-core.jar
jar --describe-module --file legacy-extra.jar
```

Lệnh này giúp xác định module name, package được nhận diện và các directive module. Nếu JAR không có `module-info.class`, kết quả có thể cho biết nó là automatic module và tên được suy ra hoặc khai báo qua manifest.

Để kiểm tra module graph trên module path:

```bash
java --validate-modules \
  --module-path mods \
  --add-modules ALL-MODULE-PATH
```

Lệnh validation có thể phát hiện xung đột package và các vấn đề module graph khác. Nếu cần xem module nào thực sự được resolve khi chạy ứng dụng:

```bash
java --module-path mods \
  --show-module-resolution \
  -m com.acme.app/com.acme.app.Main
```

Có thể dùng `jdeps` để xem dependency và kiểm tra descriptor:

```bash
jdeps --check com.acme.app --module-path mods
```

Nên kiểm tra toàn bộ tập artifact sẽ được triển khai cùng nhau. Kiểm tra từng JAR riêng lẻ không phát hiện được package bị chia giữa hai JAR.

## 8. Hướng xử lý khi chuyển sang module path

### Gom package về một module sở hữu

Nếu các class cùng package thuộc cùng một thành phần, chuyển chúng về một module duy nhất:

```text
com.acme.util
├── StringHelper
└── DateHelper
```

Module descriptor export package nếu đó là API cần cho consumer:

```java
module com.acme.util {
    exports com.acme.util;
}
```

### Tách package theo trách nhiệm

Nếu các class thuộc hai thành phần độc lập, đổi package để mỗi module sở hữu package riêng:

```text
com.acme.core.util.StringHelper
com.acme.extra.util.DateHelper
```

Cần cập nhật import, cấu hình serialization/reflection và các tên class được lưu trong cấu hình nếu chúng được tham chiếu bằng tên đầy đủ.

### Modular hóa dependency

Đưa các dependency cần thiết lên module path và tạo module descriptor phù hợp. Có thể bắt đầu bằng automatic module để xác định tên module và kiểm tra dependency, sau đó bổ sung explicit `module-info.java` để kiểm soát `requires` và `exports`.

Manifest `Automatic-Module-Name` giúp giữ tên automatic module ổn định giữa các phiên bản JAR, nhưng không sửa split package. Các package vẫn thuộc module riêng và vẫn cần được tổ chức không xung đột.

### Tạm giữ nhóm thư viện legacy trên classpath

Nếu chưa thể modular hóa toàn bộ nhóm thư viện có package phụ thuộc lẫn nhau, có thể giữ nhóm đó trên classpath và để phần ứng dụng legacy chạy trong unnamed module trong giai đoạn chuyển đổi. Tuy nhiên, named module không đọc unnamed module theo mặc định; không thể giả định một named module sẽ sử dụng trực tiếp các class legacy chỉ vì JAR nằm trên classpath.

## 9. Các cơ chế đặc biệt và giới hạn

### --patch-module

`--patch-module` cho phép bổ sung class hoặc resource vào một module đã tồn tại, khiến nội dung được patch trở thành một phần của module đích trong lần chạy đó.

Ví dụ:

```bash
java --patch-module com.acme.core=patches/core \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Đây là cơ chế có chủ đích cho một số tình huống patch hoặc kiểm thử. Nó không nên được dùng như cách sửa mặc định cho cấu trúc phát hành có package ownership không rõ ràng. Khi patch, phải xác định module đích và kiểm soát chính xác nội dung được bổ sung.

### --add-reads và --add-exports

Các tùy chọn này có thể điều chỉnh readability hoặc quyền truy cập package trong tình huống tương thích đặc biệt. Chúng không làm hai module sở hữu cùng package trở thành một module và không tự giải quyết split package.

### Automatic modules

JAR không có descriptor khi đặt trên module path có thể trở thành automatic module. Automatic module thuận tiện cho quá trình chuyển đổi, nhưng nó không phải là unnamed module của classpath. Nó vẫn có tên module, tham gia module graph và có thể gây xung đột package với module khác.

## 10. Quy trình kiểm tra trong CI

Một pipeline chuyển đổi hoặc phát hành modular nên:

1. Tạo thư mục staging chứa đúng các JAR sẽ được triển khai.
2. Quét package inventory của toàn bộ JAR để tìm package xuất hiện ở nhiều artifact.
3. Chạy `jar --describe-module` cho các dependency để xác nhận tên module và package.
4. Chạy `java --validate-modules` trên module path staging.
5. Chạy integration test bằng đúng lệnh khởi chạy modular dự kiến.
6. Kiểm tra các thư viện còn trên classpath và xác nhận không có named module nào phụ thuộc ngầm vào unnamed module.
7. Chỉ phát hành khi các bước kiểm tra bắt buộc thành công.

Với dự án đang chuyển đổi, nên chạy test cả cấu hình classpath cũ và module path mới. Sự khác biệt giữa hai kết quả giúp phát hiện dependency ẩn, package-private coupling và các package bị chia giữa artifact.

## Ghi nhớ

- Trên classpath, nhiều JAR thường cùng đóng góp class vào unnamed module của class loader; split package có thể hoạt động.
- Trên module path, package thuộc module riêng; hai module export cùng package tới một consumer đọc cả hai có thể khiến resolution thất bại.
- Cùng package name giữa named module và unnamed module không làm chúng trở thành một package dùng chung.
- Named module không đọc unnamed module theo mặc định.
- Automatic module vẫn là module và vẫn có thể tạo split-package conflict.
- Kiểm tra toàn bộ tập JAR bằng `jar --describe-module`, `java --validate-modules`, `jdeps` và integration test.
- Sửa bằng cách gom package về một module hoặc tách package theo trách nhiệm; `--patch-module` chỉ dành cho tình huống đặc biệt có kiểm soát.
