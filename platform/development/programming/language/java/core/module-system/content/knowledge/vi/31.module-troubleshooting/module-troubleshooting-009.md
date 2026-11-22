# Cách đọc --show-module-resolution và jdeps output

## 1. Hai công cụ trả lời hai câu hỏi khác nhau

Khi debug ứng dụng Java modular, cần biết module nào được đưa vào module graph lúc khởi chạy và các class trong artifact có tham chiếu tới những module nào.

Hai công cụ thường dùng là:

- **`java --show-module-resolution`** in thông tin module resolution của lần khởi chạy thực tế. Nó giúp xem root module, các quan hệ `requires` được resolve và service provider được bind.
- **`jdeps`** phân tích dependency tĩnh từ class files, JAR hoặc module. Nó giúp phát hiện module/package/class mà bytecode tham chiếu, dependency còn thiếu và descriptor có thể cần điều chỉnh.

Đây là hai góc nhìn bổ trợ nhau. `--show-module-resolution` cho biết module system đã resolve gì trong lần chạy đó; `jdeps` cho biết bytecode có những tham chiếu tĩnh nào. Không công cụ nào tự chứng minh mọi đường chạy động của ứng dụng đều đúng.

## 2. Bật --show-module-resolution

Chạy ứng dụng modular với tùy chọn này:

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Trong đó:

- `--show-module-resolution` yêu cầu launcher in thông tin resolution.
- `--module-path mods` chỉ ra thư mục chứa các module ứng dụng và dependency.
- `-m com.acme.app/com.acme.app.Main` chọn module main và main class.

Có thể kết hợp với các tùy chọn khác đang dùng trong môi trường thật, ví dụ `--add-modules`, `--limit-modules`, `--upgrade-module-path` hoặc các module path bổ sung. Khi debug, nên giữ lệnh chạy giống môi trường gặp lỗi để quan sát đúng module graph.

## 3. Đọc các dòng root, requires và binds

Đầu ra thường có các dòng thể hiện vai trò của module trong quá trình resolution. Ví dụ minh họa:

```text
root com.acme.app file:///opt/app/mods/com.acme.app.jar
com.acme.app requires com.acme.api file:///opt/app/mods/com.acme.api.jar
com.acme.api requires java.logging jrt:/java.logging
com.acme.app binds com.acme.provider.json file:///opt/app/mods/com.acme.provider.json.jar
```

Ý nghĩa:

- **`root`**: module được chọn làm root cho lần khởi chạy, thường thông qua `-m` hoặc `--add-modules`.
- **`requires`**: module cần một module khác theo dependency trong module descriptor; resolver tìm và đưa dependency đó vào graph.
- **`binds`**: module được đưa vào graph thông qua service binding, thường vì một module đã resolve khai báo `uses` cho service type mà provider cung cấp bằng `provides`.

Tên module và đường dẫn hiển thị phụ thuộc vào JDK, module finder và nguồn module. Ví dụ trên chỉ minh họa cách đọc vai trò của từng dòng, không phải output cố định của mọi ứng dụng.

Một module xuất hiện trong output không có nghĩa main code đã gọi mọi class của module đó. Resolution diễn ra ở cấp module trước khi ứng dụng thực thi các đường code cụ thể.

## 4. Dùng output để lần theo dependency

Giả sử ứng dụng báo thiếu module `com.acme.api`. Hãy tìm dòng `requires` dẫn tới module này:

```text
root com.acme.app ...
com.acme.app requires com.acme.api ...
```

Sau đó kiểm tra:

1. Module `com.acme.api` có thực sự nằm trong module path không?
2. Tên trong `requires` có khớp với module name trong JAR không?
3. Module path của lệnh chạy có giống cấu hình build/test không?
4. Có dùng `--limit-modules` khiến module hoặc dependency bị loại khỏi universe không?
5. Module có phải provider được tìm qua service binding và bị thiếu khỏi nguồn module có thể quan sát không?

Nếu output có dòng `binds`, đó là dấu hiệu service binding đã bổ sung provider vào graph. Nếu provider không xuất hiện, kiểm tra consumer có khai báo `uses`, provider có khai báo `provides`, và provider có nằm trong các module finder/parent configuration mà resolver quan sát được không.

Không nên suy luận rằng mọi module không xuất hiện trong output đều bị thiếu. Có thể module đó không phải root hoặc dependency cần thiết cho lần chạy hiện tại.

## 5. Dùng jdeps để xem dependency tổng quan

`jdeps` là công cụ phân tích dependency tĩnh của class files và JAR. Để xem dependency ở mức module/package tổng quan, dùng:

```bash
jdeps --summary app.jar
```

Ví dụ output:

```text
app.jar -> java.base
app.jar -> java.logging
app.jar -> com.acme.api
```

Cách đọc:

- Cột bên trái là artifact đang được phân tích.
- Cột bên phải là module mà artifact có dependency tĩnh tới.
- `java.base` là dependency nền tảng thường xuất hiện trong hầu hết Java code.
- `java.logging` cho biết bytecode tham chiếu API thuộc module đó.
- `com.acme.api` là dependency ứng dụng cần được cung cấp trong module path hoặc môi trường phân tích phù hợp.

Output thực tế có thể hiển thị tên JAR, tên module hoặc tên package tùy tùy chọn và loại artifact.

Nếu phân tích một modular JAR cùng dependency trên module path:

```bash
jdeps --module-path mods --summary mods/com.acme.app.jar
```

`--module-path` giúp jdeps tìm các module phụ thuộc để ánh xạ tham chiếu. Nếu dependency không có trong module path, báo cáo có thể chỉ ra package hoặc module không được phân giải.

## 6. Liệt kê dependency ở mức module

Để xem các module dependency:

```bash
jdeps --module-path mods --list-deps mods/com.acme.app.jar
```

Output minh họa:

```text
   java.base
   java.logging
   com.acme.api
```

Dùng `--print-module-deps` khi cần danh sách tên module phân tách bằng dấu phẩy, thường hữu ích khi tạo runtime image với `jlink`:

```bash
jdeps --module-path mods \
  --print-module-deps mods/com.acme.app.jar
```

Ví dụ:

```text
java.base,java.logging,com.acme.api
```

Danh sách này được suy ra từ dependency tĩnh mà jdeps phát hiện. Nếu ứng dụng nạp module qua reflection, tên class được đọc từ cấu hình, ServiceLoader hoặc cơ chế plugin động, cần kiểm tra thêm vì các dependency đó có thể không xuất hiện đầy đủ trong phân tích bytecode.

## 7. Xem dependency ở mức class

Khi cần tìm class nào tạo ra dependency, dùng chế độ verbose:

```bash
jdeps -verbose:class --module-path mods mods/com.acme.app.jar
```

Output minh họa:

```text
com.acme.app.Main -> com.acme.api.Customer com.acme.api
com.acme.app.Main -> java.lang.Object java.base
com.acme.app.Main -> java.util.logging.Logger java.logging
```

Mỗi dòng cho biết class nguồn tham chiếu tới class đích và module/package liên quan theo định dạng của phiên bản JDK.

Cách đọc:

- Xác định class bên trái để biết phần code nào tạo ra dependency.
- Xác định class bên phải để tìm API được tham chiếu.
- Kiểm tra module sở hữu class đích có nằm trong module path và có được consumer đọc hay không.

Có thể dùng `-verbose:package` để xem dependency ở mức package, hoặc `-verbose:module` để xem ở mức module. Các chế độ verbose làm output dài hơn; chỉ dùng khi cần truy ra nguồn dependency.

## 8. Tìm dependency bị thiếu

Khi nghi ngờ JAR tham chiếu tới package không có trong các module được cung cấp, dùng:

```bash
jdeps --missing-deps --module-path mods mods/com.acme.app.jar
```

Tùy artifact và JDK, output có thể chỉ ra class nguồn và class đích không tìm được. Ví dụ minh họa:

```text
com.acme.app.Main -> com.acme.legacy.LegacyClient not found
```

Điều này cho biết bytecode có tham chiếu tĩnh tới class mà jdeps không thể phân giải trong phạm vi phân tích hiện tại.

Cần phân biệt:

- **Module không tìm thấy lúc resolution:** module graph không thể resolve dependency được khai báo.
- **Class/package không tìm thấy trong jdeps:** công cụ không tìm được class đích từ artifact và module path đang phân tích.
- **ClassNotFoundException/NoClassDefFoundError lúc runtime:** class không được tìm thấy hoặc không thể định nghĩa/nạp trong class loader ở đường chạy thực tế.

Ba trường hợp có liên quan nhưng không đồng nghĩa. Hãy dùng thông báo lỗi, module path, classpath và class loader thực tế để xác định nguyên nhân.

## 9. Kiểm tra module descriptor với jdeps --check

Với named module, có thể kiểm tra descriptor và dependency:

```bash
jdeps --module-path mods --check com.acme.app
```

Tùy phiên bản JDK và cấu hình module, báo cáo có thể cho biết:

- Module descriptor hiện tại.
- Dependency mà jdeps suy ra từ bytecode.
- Những dependency cần được xem xét thêm hoặc có thể được loại bỏ.
- Các khác biệt giữa descriptor và dependency tĩnh.

Không nên tự động thay toàn bộ `module-info.java` bằng đề xuất của công cụ. Descriptor còn thể hiện API chủ ý của module, chẳng hạn `requires transitive`, `requires static`, `uses` và `provides`; một số quan hệ dịch vụ hoặc phụ thuộc động không thể suy ra chỉ từ bytecode.

Đặc biệt, jdeps phân tích tham chiếu tĩnh và không quyết định thay nhà phát triển module nào phải được export cho consumer. Khi thấy package không visible, vẫn cần kiểm tra `requires` và `exports` trong module descriptor.

## 10. Kết hợp hai công cụ để chẩn đoán

Ví dụ ứng dụng khởi chạy nhưng thiếu provider hoặc báo không tìm thấy dependency:

**Bước 1: xem module graph thực tế**

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.app/com.acme.app.Main
```

Ghi lại root, các dependency `requires` và các provider được `binds`.

**Bước 2: phân tích dependency tĩnh**

```bash
jdeps --module-path mods \
  --summary mods/com.acme.app.jar
```

So sánh module được bytecode tham chiếu với module thực sự có trong graph.

**Bước 3: tìm class tạo dependency**

```bash
jdeps -verbose:class --module-path mods mods/com.acme.app.jar
```

Dùng output để xác định class nguồn và class đích.

**Bước 4: kiểm tra dependency bị thiếu**

```bash
jdeps --missing-deps --module-path mods mods/com.acme.app.jar
```

**Bước 5: kiểm tra descriptor**

```bash
jdeps --module-path mods --check com.acme.app
jar --describe-module --file mods/com.acme.api.jar
```

Đối chiếu các dependency với `requires`, các package consumer cần với `exports`, và service type với `uses`/`provides`.

## 11. Những gì jdeps không thể kết luận

`jdeps` là phân tích tĩnh. Nó không thực thi ứng dụng và không thể luôn phát hiện:

- Class được nạp bằng `Class.forName` với tên lấy từ file cấu hình hoặc database.
- Plugin được tìm động trong thư mục bên ngoài module path ban đầu.
- Service provider được tìm bằng `ServiceLoader` khi quan hệ service không thể suy ra từ bytecode.
- Dependency chỉ xuất hiện trong một đường chạy chưa được phân tích hoặc trong dữ liệu runtime.
- Hành vi của class loader tùy chỉnh, instrumentation hoặc framework.

Tương tự, `--show-module-resolution` chỉ mô tả module resolution của lần khởi chạy cụ thể. Nó không liệt kê mọi class đã được tải, mọi method đã chạy hoặc mọi dependency tiềm ẩn của tất cả cấu hình khác.

Vì vậy, kết quả của hai công cụ cần được kết hợp với module descriptor, cấu hình runtime, test tích hợp và log lỗi thực tế.

## 12. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
|---|---|
| Xem module graph khi chạy | `java --show-module-resolution ...` |
| Xem dependency tổng quan | `jdeps --summary app.jar` |
| Liệt kê module dependency | `jdeps --list-deps app.jar` |
| In danh sách module dependency | `jdeps --print-module-deps app.jar` |
| Xem dependency theo class | `jdeps -verbose:class app.jar` |
| Xem dependency bị thiếu | `jdeps --missing-deps app.jar` |
| Kiểm tra module descriptor | `jdeps --check module.name` |
| Xem descriptor và package của JAR | `jar --describe-module --file app.jar` |

Khi dùng các lệnh cần resolve dependency, thêm `--module-path mods` với thư mục chứa các module liên quan.

## Ghi nhớ

- `--show-module-resolution` cho biết root, dependency và service binding của lần khởi chạy.
- Dòng `requires` thể hiện dependency module; dòng `binds` thể hiện provider được thêm nhờ service binding.
- `jdeps` phân tích dependency tĩnh từ class files/JAR; `--summary`, `--list-deps`, `--print-module-deps` và `-verbose:class` cung cấp các mức chi tiết khác nhau.
- `--missing-deps` hỗ trợ tìm tham chiếu class không được phân giải trong phạm vi phân tích.
- `jdeps --check` giúp đối chiếu descriptor với dependency tĩnh, nhưng không thay thế quyết định thiết kế module.
- Hai công cụ bổ trợ nhau; cần kiểm tra thêm reflection, ServiceLoader, plugin động và test runtime.
