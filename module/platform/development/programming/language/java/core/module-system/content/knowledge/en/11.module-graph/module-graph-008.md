# Kiểm tra module graph bằng jdeps và runtime options

## 1. Mục tiêu

Khi ứng dụng dùng Java Platform Module System (JPMS), tệp `module-info.java` cho biết module nào phụ thuộc module nào, package nào được xuất ra ngoài và package nào được mở cho reflection. Tuy nhiên, descriptor đúng cú pháp chưa đủ bảo đảm chương trình phân giải module thành công khi chạy.

Sau bài này, bạn có thể:

- Đọc và mô tả **module graph** từ các quan hệ `requires`, `requires transitive` và `requires static`.
- Dùng **`jdeps`** để kiểm tra phụ thuộc tĩnh từ bytecode, tìm phụ thuộc JDK, rà soát descriptor và xuất đồ thị.
- Dùng các tùy chọn của **`java` launcher** để xem module nào được quan sát, module nào được phân giải và nguyên nhân lỗi tại runtime.
- Phân biệt lỗi **module không được phân giải**, **không có quan hệ đọc**, **package không được export** và **package không được open**.
- Xác định giới hạn của phân tích tĩnh khi ứng dụng dùng reflection, `ServiceLoader` hoặc tải lớp động.

Các ví dụ sử dụng Java 17 trở lên; các lệnh JPMS nền tảng đã có từ Java 9.

## 2. Module graph thực sự chứa gì?

Module graph có các **đỉnh** là module đã được phân giải và các **cạnh đọc** biểu diễn quan hệ mà một module có thể đọc module khác. Descriptor `module-info.java` khai báo các phụ thuộc cần thiết để hệ thống tạo graph. Mỗi named module mặc nhiên phụ thuộc `java.base`, kể cả khi không ghi `requires java.base;`.

Ví dụ:

```java
// module com.demo.api
module com.demo.api {
    exports com.demo.api;
}

// module com.demo.app
module com.demo.app {
    requires com.demo.api;
}
```

Khi `com.demo.app` là module gốc, graph tối thiểu có quan hệ:

```text
com.demo.app ----requires----> com.demo.api
     |                              |
     +----------> java.base <-------+
                 (ngầm định)
```

Ba cơ chế cần phân biệt:

| Khái niệm | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| **Resolution** | Module được tìm thấy và đưa vào tập module đã phân giải | `java --show-module-resolution`, `--validate-modules` |
| **Readability** | Module A có quyền đọc module B | `requires`, `requires transitive`, `--add-reads` |
| **Accessibility** | Một kiểu thuộc package được truy cập hợp lệ theo `exports` hoặc `opens` | `module-info.java`, thông báo lỗi compile/runtime, `--add-exports`/`--add-opens` |

**Được đọc không đồng nghĩa được truy cập mọi package.** Ví dụ `com.demo.app` đọc được `com.demo.api` nhưng vẫn không thể sử dụng public class trong package mà `com.demo.api` không `exports`. Tương tự, `exports` phục vụ truy cập thông thường; deep reflection vào thành viên private thường cần `opens`.

Các dạng khai báo quan trọng:

```java
requires com.demo.api;                 // phụ thuộc trực tiếp
requires transitive com.demo.api;      // module đọc module hiện tại cũng đọc được api
requires static com.demo.annotations;  // cần khi biên dịch; có thể vắng mặt lúc chạy
exports com.demo.api;
exports com.demo.internal to com.demo.friend; // export có điều kiện
opens com.demo.model to com.demo.framework;   // cho phép deep reflection có điều kiện
```

`requires transitive` có ý nghĩa với thiết kế API: nếu `com.demo.facade` khai báo `requires transitive com.demo.api`, module yêu cầu `com.demo.facade` có thể đọc `com.demo.api` theo quan hệ truyền tiếp. `requires static` cho phép dependency không xuất hiện tại runtime, nhưng **không bảo đảm đoạn mã thực sự dùng dependency đó vẫn chạy** nếu lớp cần thiết vắng mặt.

## 3. Dựng dự án mẫu có hai module

Cấu trúc nguồn:

```text
src/
  com.demo.api/
    module-info.java
    com/demo/api/Message.java
  com.demo.app/
    module-info.java
    com/demo/app/Main.java
```

Nội dung của từng tệp:

**`src/com.demo.api/module-info.java`**

```java
module com.demo.api {
    exports com.demo.api;
}
```

**`src/com.demo.api/com/demo/api/Message.java`**

```java
package com.demo.api;

public final class Message {
    private Message() {}

    public static String text() {
        return "Hello from JPMS";
    }
}
```

**`src/com.demo.app/module-info.java`**

```java
module com.demo.app {
    requires com.demo.api;
}
```

**`src/com.demo.app/com/demo/app/Main.java`**

```java
package com.demo.app;

import com.demo.api.Message;

public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
```

Biên dịch các module từ thư mục gốc của dự án:

```sh
mkdir mods
javac --module-source-path src -d mods -m com.demo.api,com.demo.app
java --module-path mods -m com.demo.app/com.demo.app.Main
```

Kết quả chương trình:

```text
Hello from JPMS
```

`mods` chứa các **exploded modules** (thư mục có `module-info.class` và các class); `--module-path` cũng có thể trỏ đến thư mục chứa modular JAR. Trong môi trường thực tế, cần kiểm tra đúng đường dẫn module ở cả bước build và bước chạy.

## 4. Phân tích phụ thuộc tĩnh bằng jdeps

`jdeps` nằm trong JDK và đọc class/JAR để báo cáo dependency. Lệnh này rất hữu ích trước khi đóng gói, khi nâng cấp Java hoặc khi chuyển ứng dụng từ classpath sang module path.

### 4.1. Xem phụ thuộc gọn bằng `--summary`

```sh
jdeps --module-path mods --module com.demo.app --summary
```

Bạn cần tìm cạnh `com.demo.app -> com.demo.api` và các phụ thuộc nền tảng liên quan. Hình thức và số dòng hiển thị phụ thuộc JDK, chế độ phân tích và việc dùng `--recursive`; đừng coi ví dụ diễn giải graph là một stdout cố định cho mọi phiên bản.

Để mở rộng sang phụ thuộc gián tiếp:

```sh
jdeps --module-path mods --module com.demo.app --recursive --summary
```

`--recursive` yêu cầu theo dõi quan hệ phụ thuộc đệ quy, hữu ích khi ứng dụng có nhiều module trung gian.

### 4.2. Liệt kê module cần thiết để chạy

```sh
jdeps --module-path mods --module com.demo.app --list-deps
```

Nếu cần truyền danh sách module cho một bước build hoặc công cụ khác:

```sh
jdeps --module-path mods --module com.demo.app --print-module-deps
```

`--list-deps` in các module phụ thuộc dưới dạng danh sách; `--print-module-deps` tạo danh sách phân tách bằng dấu phẩy. Hai tùy chọn hữu ích cho việc đánh giá tập module cần thiết, chẳng hạn trước khi cân nhắc dùng `jlink`. Tuy nhiên, các phụ thuộc chỉ xuất hiện qua reflection, service configuration hoặc nạp động có thể không được nhận diện đầy đủ.

### 4.3. Kiểm tra descriptor và graph đã rút gọn

```sh
jdeps --module-path mods --check com.demo.app
```

`--check` kiểm tra quan hệ module cho named module, giúp xem descriptor khai báo, graph sau phân tích và các cạnh có thể rút gọn. Đặc biệt hữu ích khi có nhiều tầng `requires transitive` khiến khai báo phụ thuộc bị dư hoặc khó hiểu.

Đọc kết quả theo hướng:

1. Những module nào được khai báo trong descriptor?
2. Những phụ thuộc nào thực tế cần thiết để module đọc các kiểu đang dùng?
3. Có cạnh nào được thừa hưởng qua `requires transitive`?
4. Graph rút gọn có khớp ý định thiết kế hay cần xem lại `module-info.java`?

Không xóa `requires` chỉ vì một lần chạy công cụ không quan sát được quan hệ trong bytecode: còn có compile-time API, service, reflection và các điều kiện triển khai khác.

### 4.4. Xuất đồ thị DOT

```sh
jdeps --module-path mods --module com.demo.app --dot-output build/module-graph
```

`jdeps` ghi các tệp `.dot` vào thư mục đầu ra. Nếu có Graphviz, có thể chuyển tệp DOT phù hợp sang SVG hoặc PNG để đọc đồ thị lớn. Đây là kết quả **phân tích tĩnh** theo tập module và tùy chọn đã cấp, không phải bản ghi chính xác mọi lớp được nạp lúc chạy.

### 4.5. Rà soát API nội bộ của JDK

```sh
jdeps --jdk-internals --module-path mods --module com.demo.app
```

Tùy chọn `--jdk-internals` giúp phát hiện tham chiếu bytecode tới các JDK internal APIs, ví dụ kiểu thuộc `sun.*`. Những API này có thể bị che bởi module encapsulation hoặc thay đổi ở JDK mới. Ưu tiên API công khai thay cho việc cố mở package nội bộ bằng runtime flags.

Với **multi-release JAR**, chỉ định phiên bản đích khi cần phân tích các class tương ứng:

```sh
jdeps --multi-release 17 --print-module-deps path/to/app.jar
```

Thay `17` bằng phiên bản Java thực tế muốn kiểm tra. Báo cáo có thể khác nhau giữa các phiên bản vì những class được chọn khác nhau.

## 5. Quan sát module graph ở runtime

`jdeps` trả lời: “bytecode đang tham chiếu tới đâu?”. Runtime options trả lời: “launcher đã quan sát và phân giải module nào trong lần khởi động này?”.

### 5.1. Xem module đang quan sát được

```sh
java --module-path mods --list-modules
```

Kết quả bao gồm các module hệ thống và named module quan sát được trên module path. Đây **không phải** bằng chứng rằng tất cả module được liệt kê đều đã được phân giải vào graph của ứng dụng cụ thể.

### 5.2. Xem descriptor mà launcher nhận diện

```sh
java --module-path mods --describe-module com.demo.app
java --module-path mods --describe-module com.demo.api
```

Kiểm tra tên module, `requires`, `exports` và các thông tin descriptor khác. Lệnh này rất hữu ích để phát hiện nhầm tên module, bản JAR cũ hoặc descriptor khác với source đang mở.

### 5.3. In tiến trình phân giải module

```sh
java --show-module-resolution --module-path mods \
  -m com.demo.app/com.demo.app.Main
```

Trong PowerShell hoặc CMD, dùng **một dòng** thay cho dấu nối dòng `\` kiểu shell Unix:

```text
java --show-module-resolution --module-path mods -m com.demo.app/com.demo.app.Main
```

Launcher in thông tin lựa chọn module gốc, module được giải quyết qua phụ thuộc, vị trí module và các quan hệ liên quan, rồi thực thi `main`. Đọc thông báo theo câu hỏi:

- `com.demo.app` có được chọn làm root module không?
- `com.demo.api` được tìm trên module path nào?
- Các module hệ thống phát sinh từ `requires` nào?
- Module mong đợi có xuất hiện trong kết quả phân giải không?

**Quan trọng:** các module quan sát được (`--list-modules`) và các module đã được phân giải (`--show-module-resolution`) là hai tập khác nhau. Một module tồn tại trên đường dẫn nhưng chưa chắc được thêm vào runtime graph.

### 5.4. Xác thực tính nhất quán của các module quan sát được

```sh
java --module-path mods --validate-modules
```

`--validate-modules` hữu ích để sớm phát hiện vấn đề với module path, ví dụ trùng module hoặc xung đột package trước khi chạy chương trình. Một lần xác thực thành công không đồng nghĩa mọi đường chạy nghiệp vụ hay reflection đều đúng.

## 6. Những runtime options tác động đến graph hoặc quyền truy cập

Các tùy chọn dưới đây phục vụ chẩn đoán, tương thích tạm thời và tích hợp thư viện. Trong mã nguồn do mình quản lý, ưu tiên sửa descriptor hoặc cấu trúc module cho đúng thiết kế.

| Tùy chọn | Tác dụng | Cần nhớ |
|---|---|---|
| `--module-path <path>` | Chỉ định nơi tìm application modules | Phải dùng đúng artifact đã build |
| `--add-modules <names>` | Thêm root modules để resolver xem xét | Có thể làm phát sinh phụ thuộc gián tiếp |
| `--limit-modules <names>` | Giới hạn tập module quan sát được | Có thể làm module đang cần trở nên không khả dụng |
| `--add-reads A=B` | Thêm cạnh đọc từ A sang B | Không tự export package ở B |
| `--add-exports A/pkg=B` | Cho B truy cập package `pkg` của A | Phục vụ truy cập kiểu thông thường |
| `--add-opens A/pkg=B` | Mở package `pkg` của A cho deep reflection từ B | Không thay thế `requires` trong thiết kế chuẩn |
| `--patch-module A=<path>` | Bổ sung/ghi đè nội dung của module A khi khởi chạy | Chủ yếu dùng công cụ hoặc môi trường kiểm thử |

Ví dụ thêm một module hệ thống làm root và thêm quan hệ đọc tạm thời:

```sh
java --module-path mods \
  --add-modules java.sql \
  --add-reads com.demo.app=java.sql \
  -m com.demo.app/com.demo.app.Main
```

Trong trường hợp cần truy cập một package nội bộ đã tồn tại trong module `com.demo.api`:

```sh
java --module-path mods \
  --add-exports com.demo.api/com.demo.internal=com.demo.app \
  -m com.demo.app/com.demo.app.Main
```

Nếu framework truy cập constructor hoặc field private bằng reflection, tình huống tương ứng có thể cần:

```sh
java --module-path mods \
  --add-opens com.demo.api/com.demo.internal=com.demo.app \
  -m com.demo.app/com.demo.app.Main
```

Hai ví dụ cuối chỉ có ý nghĩa khi `com.demo.internal` thực sự tồn tại trong artifact. Nếu target chạy từ **classpath (unnamed module)**, có thể gặp cú pháp đích `ALL-UNNAMED` thay cho một named module.

Một số nguyên tắc sử dụng:

- `--add-reads` chỉ tạo quyền đọc; truy cập vào package vẫn tuân theo `exports`/`opens`.
- `--add-exports` mở quyền truy cập package cho code thông thường; `--add-opens` dành cho quyền reflection sâu.
- `--add-modules` giải quyết bài toán chọn root modules, không thay thế quyền truy cập.
- `--limit-modules` hữu ích khi kiểm tra ảnh hưởng của tập module bị thu hẹp, nhưng dễ loại bỏ dependency cần thiết nếu dùng tùy tiện.
- Runtime flags là **override cho lần chạy đó**. Chúng không tự sửa `module-info.class`, không thay đổi kết quả compile mặc định và có thể cần cấu hình riêng tại lúc biên dịch.

## 7. Quy trình đối chiếu tĩnh và động

Khi chuyển một ứng dụng sang JPMS hoặc điều tra lỗi startup, hãy chạy theo thứ tự:

**Bước 1 — Xác định artifact thật đang chạy.** Kiểm tra thư mục `mods`/`libs`, module path và main module. Một lần build thành công không chứng minh launcher dùng đúng JAR mới nhất.

**Bước 2 — Xem descriptor.**

```sh
java --module-path mods --describe-module com.demo.app
```

**Bước 3 — Phân tích phụ thuộc từ bytecode.**

```sh
jdeps --module-path mods --module com.demo.app --summary
jdeps --module-path mods --check com.demo.app
```

**Bước 4 — Xác thực module path.**

```sh
java --module-path mods --validate-modules
```

**Bước 5 — Chạy và theo dõi resolver.**

```sh
java --show-module-resolution --module-path mods -m com.demo.app/com.demo.app.Main
```

**Bước 6 — Phân loại lỗi theo thông báo thực tế.** Nếu graph đúng mà chương trình vẫn lỗi khi dùng reflection, service hoặc dynamic class loading, điều tra cơ chế runtime đó; không kết luận `jdeps` đã bao phủ mọi phụ thuộc.

Khi so sánh, phân biệt ba câu hỏi:

1. `jdeps` phát hiện **tham chiếu trong bytecode** nào?
2. `module-info.java` tuyên bố **các module phải đọc** và **package được công khai** ra sao?
3. Launcher thực tế **đã phân giải** module nào khi chạy với đúng bộ options và artifact?

Chênh lệch giữa các câu trả lời này thường chỉ thẳng vào nguyên nhân vấn đề.

## 8. Các lỗi thường gặp và hướng xử lý

### 8.1. `Module ... not found, required by ...`

**Triệu chứng:** launcher hoặc compiler không tìm thấy module mà descriptor yêu cầu.

**Kiểm tra:** tên module trong `requires`, thư mục/JAR trên `--module-path`, tên module thực bằng `--describe-module`, sự khác biệt giữa compile path và runtime path.

**Xử lý:** cung cấp đúng modular JAR/exploded module, sửa tên hoặc cập nhật bản build. Tránh dùng `--add-reads` để xử lý lỗi module chưa được tìm thấy; phải giải quyết resolution trước.

### 8.2. `package ... is not visible` hoặc `does not export ...`

**Triệu chứng:** module đọc được dependency nhưng package được tham chiếu không export cho bên gọi.

**Kiểm tra:** `exports` trong module cung cấp; nếu dùng `exports ... to ...`, kiểm tra chính xác tên module được phép.

**Xử lý:** xuất public API hợp lệ hoặc điều chỉnh cách tổ chức package. Với mã cũ, `--add-exports` chỉ là biện pháp tạm thời phù hợp khi đã hiểu quan hệ truy cập.

### 8.3. `InaccessibleObjectException` khi reflection

**Triệu chứng:** code dùng reflection vào thành viên không public của package chưa mở.

**Kiểm tra:** thông báo `does not "opens"`, framework truy cập package nào, module gọi có tên hay `ALL-UNNAMED`.

**Xử lý:** nếu kiến trúc yêu cầu reflection, thêm `opens pkg` hoặc `opens pkg to module` trong descriptor của module sở hữu package; dùng `--add-opens` như phương án runtime khi thích hợp.

### 8.4. `ResolutionException` / trùng module / split package

**Triệu chứng:** xung đột khi resolver xử lý nhiều module định nghĩa tên trùng nhau hoặc chứa các package không thể cùng tồn tại trong quan hệ phân giải.

**Kiểm tra:** chạy `--validate-modules`; rà soát module path, dependency transitives, các JAR đóng gói trùng class/package.

**Xử lý:** loại bỏ artifact trùng, thống nhất phiên bản thư viện hoặc tái tổ chức package. Java modules không phải cơ chế để cho phép các named modules tùy ý chia sẻ một package.

### 8.5. `ClassNotFoundException` hoặc `NoClassDefFoundError` dù `jdeps` trông hợp lý

**Triệu chứng:** ứng dụng khởi động được nhưng thất bại ở nhánh dùng reflection, plugin, SPI hoặc lớp chỉ nạp khi có cấu hình.

**Kiểm tra:** tên class động, class loader thực tế, module có được phân giải không, package có được export/open không và khai báo `uses`/`provides` cho ServiceLoader.

**Xử lý:** thêm module cần thiết vào graph bằng thiết kế descriptor hoặc root modules phù hợp, thiết lập service đúng và kiểm tra đường chạy thực tế. Không coi một báo cáo `jdeps` trống là bằng chứng không có dependency runtime.

## 9. Giới hạn của jdeps cần ghi nhớ

`jdeps` đọc **class files và module descriptors**, nên rất mạnh với tham chiếu tĩnh nhưng không thực thi ứng dụng. Vì vậy:

- Phụ thuộc tạo bởi `Class.forName(...)`, reflection hoặc tên class đọc từ cấu hình có thể không xuất hiện.
- Quan hệ dịch vụ `uses`/`provides` và service binding cần được xem trong descriptor và cách ứng dụng khởi chạy; không nên suy luận toàn bộ từ import/bytecode.
- Automatic modules, unnamed module trên classpath và named modules có quy tắc khác nhau; kiểm tra ứng dụng đang đặt JAR ở **classpath** hay **module path**.
- Một module đọc được module khác vẫn có thể không truy cập được package vì quy tắc strong encapsulation.
- Đồ thị phụ thuộc tĩnh không thay thế việc chạy thử ứng dụng với đúng JDK, module path, tham số runtime và các nhánh nghiệp vụ cần thiết.

Đặc biệt, khi kết quả `jdeps` và `--show-module-resolution` khác nhau, hãy kiểm tra **tập root modules**, các `requires` trực tiếp/truyền tiếp, việc đưa module vào bằng `--add-modules`, cũng như các dependency chỉ được dùng qua cơ chế động.

## 10. Bài thực hành

**Bài 1 — Xác định cạnh phụ thuộc.** Với dự án mẫu, chạy `jdeps --summary` và `java --show-module-resolution`. Ghi lại: module gốc, cạnh từ `com.demo.app` tới `com.demo.api` và `java.base`. Giải thích vì sao `java.base` có thể xuất hiện dù descriptor không khai báo tường minh.

**Bài 2 — Phân biệt resolution với accessibility.** Bỏ `exports com.demo.api;` khỏi module API rồi biên dịch lại. Quan sát lỗi ở ứng dụng. Phục hồi `exports` và giải thích vì sao chỉ có `requires com.demo.api;` không đủ để truy cập `Message`.

**Bài 3 — Kiểm tra module path.** Thử chạy ứng dụng khi `--module-path` thiếu `com.demo.api`. Đọc lỗi, sau đó khôi phục đường dẫn và chạy `--validate-modules` cùng `--show-module-resolution` để xác nhận graph.

**Bài 4 — Mở rộng graph.** Thêm module `com.demo.facade` với `requires transitive com.demo.api;`. Cho `com.demo.app` phụ thuộc `com.demo.facade` và đánh giá khả năng đọc `com.demo.api`. So sánh descriptor với đầu ra `jdeps --check` để nhận biết phụ thuộc trực tiếp và truyền tiếp.

## 11. Ghi nhớ khi làm việc thực tế

- **`jdeps`**: bắt đầu với `--summary`; dùng `--list-deps` hoặc `--print-module-deps` cho danh sách module; dùng `--check` khi nghi descriptor/graph phức tạp; dùng `--jdk-internals` khi nâng cấp JDK.
- **`java` launcher**: `--list-modules` trả lời “có thể thấy gì”; `--describe-module` trả lời “descriptor nói gì”; `--show-module-resolution` trả lời “resolver đã chọn gì”; `--validate-modules` giúp phát hiện xung đột module path.
- **Chẩn đoán đúng tầng**: tìm module trước, xác nhận readability tiếp theo, rồi kiểm tra `exports`/`opens` và cơ chế tải lớp.
- **Giữ graph minh bạch**: sửa `module-info.java` và cấu trúc dependency khi sở hữu mã nguồn; dùng `--add-reads`, `--add-exports` và `--add-opens` có mục tiêu rõ ràng khi xử lý tương thích.

Có thể xem cú pháp theo JDK đang dùng bằng `jdeps --help` và `java --help`; kết quả trực tiếp từ bản JDK và artifact thực tế là căn cứ để chẩn đoán.