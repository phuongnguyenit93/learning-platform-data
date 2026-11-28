# Phân biệt hiệu lực compile-time với runtime của tùy chọn truy cập

> **Chương:** Đóng gói JDK  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu các cơ chế đóng gói JDK vẫn áp dụng trong Java hiện đại. Bài này phân biệt quyền truy cập được kiểm tra khi biên dịch với quyền truy cập được thực thi khi chạy, tập trung vào `--add-exports`, `--add-opens` và module descriptor.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi truy cập module tại compile-time và runtime.
- Giải thích hiệu lực của `requires`, `exports` và `opens` trong `module-info.java`.
- Dùng `--add-exports` ở bước biên dịch và bước chạy.
- Hiểu vì sao `--add-opens` chỉ có ý nghĩa ở runtime.
- Phân biệt `--add-exports`, `--add-opens` và `--add-reads`.
- Hiểu sự khác nhau giữa named module và unnamed module.
- Chẩn đoán trường hợp biên dịch thành công nhưng runtime vẫn ném lỗi truy cập.
- Xử lý dependency cũ mà không dựa vào `--illegal-access` đã obsolete.

## 1. Compile-time và runtime kiểm tra hai thời điểm khác nhau

Trong ứng dụng modular, quyền truy cập được kiểm tra ở nhiều giai đoạn.

**Compile-time** là giai đoạn compiler kiểm tra mã nguồn. Compiler cần biết module hiện tại có đọc được dependency không, package có được export không và kiểu/thành viên được truy cập có hợp lệ theo quy tắc Java không.

**Runtime** là giai đoạn JVM nạp module và thực thi ứng dụng. JVM tiếp tục áp dụng module graph, quyền truy cập package và quy tắc reflection. Một chương trình biên dịch thành công vẫn có thể thất bại khi chạy nếu cấu hình module runtime không tương ứng hoặc mã thực hiện deep reflection vào package chưa được mở.

Ví dụ, ứng dụng có thể được biên dịch với quyền export bổ sung để dùng một package nội bộ của JDK. Nếu lúc chạy không có quyền tương ứng, JVM có thể chặn truy cập và ném `IllegalAccessError`.

Ngược lại, reflection vào trường private thường không cần compiler nhìn thấy trường đó. Quyền truy cập sâu chỉ được kiểm tra khi mã reflection chạy; nếu package chưa được mở, thao tác có thể thất bại với `InaccessibleObjectException` hoặc không thể bật quyền truy cập sâu.

| Thời điểm | Câu hỏi chính | Cấu hình thường liên quan |
| --- | --- | --- |
| Compile-time | Compiler có được đọc module và truy cập package/kiểu này không? | `requires`, `exports`, `--add-reads`, `--add-exports` |
| Runtime, truy cập Java thông thường | JVM có cho phép mã đã biên dịch truy cập package/kiểu này không? | Module graph, `exports`, `--add-reads`, `--add-exports` |
| Runtime, deep reflection | Mã reflection có được phép truy cập sâu vào package không? | `opens`, `--add-opens` |

## 2. Module descriptor có hiệu lực xuyên suốt vòng đời module

Các chỉ thị trong `module-info.java` là khai báo cấu trúc module. Compiler dùng chúng để kiểm tra mã nguồn; JVM dùng descriptor đã biên dịch khi phân giải và thực thi module.

Ví dụ:

```java
module com.example.application {
    requires com.example.customer.api;
    exports com.example.application.api;
    opens com.example.application.model
            to com.example.persistence;
}
```

Ý nghĩa:

- `requires` khai báo dependency và readability.
- `exports` công bố package để module đọc được có thể dùng API public.
- `opens` cho phép deep reflection vào package ở runtime.
- Qualified `opens` chỉ mở package cho module được chỉ định.

Nếu package thuộc module do bạn sở hữu, khai báo đúng trong descriptor thường là giải pháp lâu dài. Các cờ dòng lệnh phù hợp hơn với tình huống cần hỗ trợ dependency cũ hoặc thử nghiệm quá trình chuyển đổi.

## 3. --add-exports có hiệu lực ở compile-time và runtime

`--add-exports` bổ sung quyền export một package từ module nguồn sang module đích. Nó cho phép truy cập Java thông thường vào các kiểu và thành viên được ngôn ngữ cho phép truy cập trong package đó.

Cú pháp tổng quát:

```text
--add-exports <module>/<package>=<target-module>
```

Có thể chỉ định nhiều module đích, phân cách bằng dấu phẩy. Cờ này có thể dùng cho cả `javac` và launcher `java`.

Ví dụ giả định ứng dụng named module cần tạm thời tham chiếu package `sun.nio.ch` trong `java.base`. Đây là JDK internal API, chỉ dùng để minh họa cơ chế chuyển đổi; không nên xây API sản phẩm phụ thuộc vào package này.

### 3.1. Cấp quyền khi biên dịch

```bash
javac --module-path mods --add-exports java.base/sun.nio.ch=com.example.application -d mods/com.example.application src/com.example.application/module-info.java src/com.example.application/com/example/application/Main.java
```

Cờ trên cho compiler biết module `com.example.application` được phép truy cập package đã chỉ định trong lần biên dịch này.

Nếu thiếu quyền compile-time, compiler có thể báo package không được export hoặc không visible. Cờ này không sửa module descriptor trên đĩa và không tự động lưu lại quyền cho những lần biên dịch sau.

### 3.2. Cấp quyền tương ứng khi chạy

```bash
java --module-path mods --add-exports java.base/sun.nio.ch=com.example.application --module com.example.application/com.example.application.Main
```

Nếu đã dùng `--add-exports` khi biên dịch nhưng quên ở runtime, chương trình có thể biên dịch thành công rồi thất bại khi thực thi đường mã truy cập package đó.

Cần quản lý cờ ở cả cấu hình build và cấu hình launcher/service. Chỉ thêm cờ trong IDE không đảm bảo môi trường production có cùng quyền.

## 4. --add-exports không mở private member cho reflection

`--add-exports` cho phép truy cập Java thông thường đến package đã export. Nó không tương đương với việc mở package cho deep reflection.

Ví dụ, export package không tự cấp quyền để framework làm việc này với trường private:

```java
Field field = target.getClass().getDeclaredField("internalState");
field.setAccessible(true);
```

Nếu package không được mở cho module gọi, thao tác deep reflection vẫn có thể bị từ chối.

Để xử lý reflection, cần `opens` trong module descriptor hoặc `--add-opens` ở runtime, tùy module có thuộc quyền chỉnh sửa của ứng dụng hay không.

## 5. --add-opens chỉ có hiệu lực ở runtime

`--add-opens` mở một package của module nguồn cho module đích thực hiện deep reflection. Nó không phải tùy chọn để compiler cho phép import một package chưa export.

Cú pháp:

```text
--add-opens <module>/<package>=<target-module>
```

Ví dụ, một thư viện cũ trong module ứng dụng cần reflection sâu vào package `java.lang`:

```bash
java --add-opens java.base/java.lang=com.example.application --module-path mods --module com.example.application/com.example.application.Main
```

Cờ này cho module `com.example.application` quyền deep reflection vào package `java.lang` của `java.base` trong lần chạy đó.

`javac` không dùng `--add-opens` để biên dịch mã nguồn. Deep reflection là thao tác runtime; compiler không cần quyền truy cập private member để biên dịch một lời gọi reflection thông qua API public như `Class` và `Field`.

Nếu ứng dụng cần mở package do chính nó sở hữu, ưu tiên khai báo:

```java
module com.example.domain {
    opens com.example.domain.model to com.example.persistence;
}
```

Khai báo này đi cùng module artifact và không cần lặp cờ launcher ở mọi môi trường chạy.

## 6. So sánh --add-exports và --add-opens

| Tiêu chí | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Mục đích | Cho phép truy cập Java thông thường đến package | Cho phép deep reflection vào package |
| Compile-time | Có thể dùng với `javac` | Không; chỉ có ý nghĩa runtime |
| Runtime | Có; cần cấp quyền tương ứng khi chạy | Có; đây là thời điểm cờ có hiệu lực |
| Import kiểu public trong package | Có thể, nếu module đọc được module nguồn | Không cấp quyền import khi biên dịch |
| Reflection vào private member | Không tự cấp quyền | Có thể cho phép |
| Phạm vi | Một package và module đích được chỉ định | Một package và module đích được chỉ định |

Đừng chọn cờ chỉ dựa trên tên lỗi. Hãy xác định mã đang cần truy cập API public hay đang thực hiện deep reflection.

## 7. --add-reads chỉ bổ sung readability

`--add-reads` bổ sung quan hệ readability giữa module nguồn và module đích:

```text
--add-reads <module>=<target-module>
```

Cờ này không export package và cũng không mở package cho reflection.

Ví dụ:

```bash
java --add-reads com.example.application=com.example.optional --module-path mods --module com.example.application/com.example.application.Main
```

Khi cần quan hệ phụ thuộc lâu dài, hãy khai báo `requires` trong module descriptor. `--add-reads` phù hợp với cấu hình chuyển tiếp, kiểm thử hoặc tình huống cần bổ sung readability ở launcher.

Nếu module đọc được module khác nhưng package chưa export, vẫn cần xử lý export. Nếu package đã export nhưng reflection sâu bị chặn, vẫn cần xử lý opens. Ba quyền không thay thế lẫn nhau.

## 8. Named module và ALL-UNNAMED

Module đích trong các cờ truy cập phải xác định đúng loại code cần được cấp quyền.

- **Named module:** module có tên, thường được xác định từ `module-info.class` hoặc module name của artifact.
- **Unnamed module:** code chạy trên classpath và không thuộc named module.

Với chương trình classpath, launcher có thể dùng `ALL-UNNAMED` để cấp quyền cho các unnamed module:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "app.jar;lib/*" com.example.Main
```

Ví dụ dùng dấu chấm phẩy cho classpath trên Windows. Trên hệ thống POSIX, dấu phân cách classpath thường là dấu hai chấm.

`ALL-UNNAMED` áp dụng cho tất cả unnamed module trong phạm vi runtime, nên có thể rộng hơn module đích cụ thể. Nếu ứng dụng dùng named module, ưu tiên chỉ rõ tên module thay vì cấp quyền cho toàn bộ classpath code.

## 9. Cấu hình module descriptor hay dùng cờ dòng lệnh?

Hãy chọn theo quyền sở hữu và mục tiêu sử dụng:

| Tình huống | Cách ưu tiên |
| --- | --- |
| Module ứng dụng cần công bố API public | `exports` trong `module-info.java` |
| Module ứng dụng cần framework reflection vào một package | Qualified `opens` trong `module-info.java` |
| Module cần đọc dependency lâu dài | `requires` hoặc `requires transitive` |
| Tạm thời truy cập package JDK internal khi chuyển đổi | `--add-exports` ở compile-time và runtime nếu cần truy cập Java thông thường |
| Thư viện cũ cần deep reflection vào package JDK | `--add-opens` ở runtime như biện pháp tạm thời |
| Thiếu readability do cấu hình module chuyển tiếp | `--add-reads` ở compile-time/runtime theo công cụ sử dụng |
| Dependency không còn hỗ trợ JDK hiện tại | Nâng cấp hoặc thay thế dependency |

Module descriptor là hợp đồng đi cùng module. Cờ launcher là cấu hình bên ngoài, có thể khác nhau giữa môi trường dev, test và production. Nếu cần quyền truy cập để ứng dụng hoạt động ổn định, hãy đưa giải pháp về đúng module descriptor hoặc thay dependency gây ra nhu cầu truy cập nội bộ.

## 10. Vì sao biên dịch thành công vẫn có thể lỗi khi chạy?

Giả sử module ứng dụng được biên dịch với:

```bash
javac --module-path mods --add-exports java.base/sun.nio.ch=com.example.application -d mods/com.example.application src/com.example.application/module-info.java src/com.example.application/com/example/application/Main.java
```

Nhưng launcher lại chạy mà thiếu cờ:

```bash
java --module-path mods --module com.example.application/com.example.application.Main
```

Compiler đã cho phép mã tham chiếu package, nhưng module graph runtime không có export bổ sung. Khi đường mã truy cập được thực thi, JVM có thể ném `IllegalAccessError`.

Vì thế, mọi cờ bổ sung dùng để biên dịch phải được đánh giá lại ở runtime. Không nên chỉ dựa vào kết quả compile để kết luận ứng dụng đã tương thích với strong encapsulation.

Một cách giảm sai lệch là lưu các cờ chuyển tiếp trong cấu hình build và launcher có quản lý, đồng thời thêm integration test chạy bằng đúng lệnh khởi động production.

## 11. Vì sao --add-opens không sửa lỗi compile-time?

Giả sử code nguồn cần import một lớp public trong package chưa export. Thêm `--add-opens` vào lệnh chạy không giúp compiler nhìn thấy package đó.

Cần export package cho module consumer, bằng module descriptor hoặc `--add-exports` ở bước biên dịch và runtime phù hợp.

Ngược lại, nếu code chỉ dùng reflection qua API public, compiler có thể biên dịch mà không cần biết lớp đích có trường private nào. Khi reflection chạy, JVM mới kiểm tra package có được mở cho caller hay không.

| Triệu chứng | Quyền cần xem xét |
| --- | --- |
| Compiler không nhìn thấy module dependency | `requires` hoặc `--add-reads` |
| Compiler không truy cập được package | `exports` hoặc `--add-exports` |
| Runtime chặn truy cập Java thông thường | Runtime readability/export tương ứng |
| Reflection không truy cập được private member | `opens` hoặc `--add-opens` |
| Module hoặc class không được tìm thấy | Module path/classpath và cấu hình phân giải; không phải lỗi opens |

## 12. Strong encapsulation trên JDK hiện đại

JDK 16 đặt strong encapsulation làm mặc định cho phần lớn JDK internals theo JEP 396. JEP 403 hoàn thiện việc đóng gói mạnh các internals trong Java 17.

Từ Java 17 trở lên, `--illegal-access` đã obsolete và không còn khôi phục cơ chế truy cập rộng như các bản Java chuyển tiếp trước đó. Không dùng `--illegal-access=permit` để xử lý lỗi trên JDK hiện đại.

Các cờ `--add-exports` và `--add-opens` vẫn có vai trò cụ thể, nhưng chúng cấp quyền cho package/module được chỉ định. Chúng không phải công tắc tắt toàn bộ strong encapsulation.

Với dependency cũ:

1. Xác định chính xác package và module gây lỗi.
2. Kiểm tra phiên bản thư viện mới có hỗ trợ JDK hiện tại không.
3. Tìm API Java SE công khai thay cho JDK internal.
4. Nếu buộc phải chuyển tiếp, cấp quyền tối thiểu cho đúng module và package.
5. Ghi lại lý do, môi trường và kế hoạch xóa cờ.
6. Chạy integration test với đúng JDK và lệnh launcher production.

## 13. Ví dụ reflection: module của ứng dụng và module JDK

### 13.1. Package thuộc module ứng dụng

Giả sử module domain có package model cần framework persistence truy cập sâu.

Khai báo trong domain:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model
            to com.example.persistence;
}
```

Module persistence cần đọc domain:

```java
module com.example.persistence {
    requires com.example.domain;
}
```

Đây là cấu hình khai báo. Khi các module được đóng gói đúng module path, JVM có thông tin opens từ descriptor và không cần thêm `--add-opens` cho package này.

### 13.2. Package thuộc module JDK

Ứng dụng không thể sửa descriptor của `java.base`. Nếu dependency cũ cần deep reflection vào package `java.lang`, có thể dùng cờ runtime hẹp trong thời gian chuyển đổi:

```bash
java --add-opens java.base/java.lang=com.example.legacy.framework --module-path mods --module com.example.application/com.example.application.Main
```

Nếu framework chạy trong unnamed module trên classpath, target có thể là `ALL-UNNAMED`. Hãy dùng đúng tên module của framework nếu có thể để tránh mở quyền rộng.

Đây chỉ là biện pháp tương thích tạm thời. Nếu framework yêu cầu truy cập sâu vào internals của JDK, cần kiểm tra hỗ trợ JDK và nâng cấp/thay thế framework.

## 14. Quản lý cờ ở build, test và production

Một nguyên nhân phổ biến của lỗi môi trường là cờ chỉ được cấu hình ở một nơi.

| Môi trường | Điều cần đồng bộ |
| --- | --- |
| IDE | Compiler arguments và VM options |
| Build compile | Cờ `javac` như `--add-exports` nếu thật sự cần |
| Unit/integration test | JVM test fork cần có runtime flags tương ứng |
| Local run | Launcher arguments tương ứng với cấu hình module |
| CI | Cùng JDK và flags như pipeline build/release |
| Production | Service launcher/container command phải mang cờ runtime cần thiết |

Không sao chép cờ vào nhiều nơi một cách thủ công nếu build tool có thể quản lý một cấu hình chung. Nhưng phải nhớ compiler options và JVM options là hai nhóm khác nhau: cờ compile-time không tự động trở thành JVM option, và cờ runtime không giúp compiler biên dịch mã nguồn.

Nếu cờ không còn cần sau khi nâng cấp dependency, xóa nó khỏi mọi cấu hình: build, IDE, test, script khởi chạy, service manager và container image.

## 15. Dùng jdeps và log để tìm nguyên nhân

`jdeps` có thể giúp phát hiện tham chiếu đến JDK internals:

```bash
jdeps --jdk-internals application.jar
```

Kết quả là đầu vào để tìm dependency cần nâng cấp. Công cụ phân tích bytecode không phát hiện đầy đủ mọi đường reflection được tạo động, vì vậy cần xem stack trace runtime và log của framework.

Khi gặp lỗi:

- Ghi nhận exception đầy đủ và module/package được nêu trong thông báo.
- Xác định lỗi xuất hiện lúc biên dịch, lúc khởi động hay khi một nhánh reflection chạy.
- Xác định module gọi và module sở hữu package.
- Kiểm tra descriptor và flags ở đúng giai đoạn.
- Tạo test tái hiện với đúng JDK mục tiêu.
- Loại bỏ cờ thử nghiệm sau khi đã sửa dependency hoặc descriptor.

Không giải quyết mọi lỗi module bằng cách thêm một danh sách `--add-opens` rộng. Điều đó làm mất ý nghĩa của module boundary và khiến cấu hình khó duy trì.

## 16. Bảng chẩn đoán compile-time và runtime

| Triệu chứng | Giai đoạn | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| `module not found` | Compile hoặc runtime resolution | Module path thiếu artifact hoặc sai tên module | Kiểm tra module path và tên module |
| `package ... is not visible` | Compile-time | Thiếu readability hoặc package chưa export | Kiểm tra `requires`, `exports`, `--add-reads`, `--add-exports` |
| Compiler báo package JDK internal không export | Compile-time | Package JDK không được export cho module ứng dụng | Ưu tiên API public; nếu chuyển tiếp, xem xét `javac --add-exports` |
| `IllegalAccessError` | Runtime | Runtime không có quyền export/readability tương ứng với lúc biên dịch | Đồng bộ module descriptor hoặc runtime flags |
| `InaccessibleObjectException` | Runtime | Deep reflection vào package chưa mở | `opens` hoặc `--add-opens` đúng caller module |
| `trySetAccessible()` trả về `false` | Runtime | Caller không được mở package hoặc quyền reflection bị giới hạn | Kiểm tra qualified opens và module gọi |
| `ClassNotFoundException` | Runtime | Class/dependency không có trong classpath/module path | Sửa đóng gói và module resolution |
| `--illegal-access` không thay đổi kết quả | Runtime JDK 17+ | Tùy chọn đã obsolete và không còn tác dụng mở rộng | Nâng cấp dependency; dùng giải pháp module cụ thể nếu cần |

## 17. Quy trình lựa chọn tùy chọn truy cập

Khi gặp lỗi, làm theo thứ tự:

1. Xác định lỗi xảy ra lúc compile-time hay runtime.
2. Xác định cần readability, truy cập API public hay deep reflection.
3. Nếu là module của ứng dụng, ưu tiên `requires`, `exports` hoặc `opens` trong descriptor.
4. Nếu dependency cũ cần truy cập JDK internal, xác định cờ phù hợp: `--add-exports` cho truy cập Java thông thường; `--add-opens` cho deep reflection.
5. Đặt cờ ở đúng giai đoạn: `javac` và `java` với `--add-exports`; chỉ runtime `java` với `--add-opens`.
6. Dùng module đích cụ thể; chỉ dùng `ALL-UNNAMED` khi thật sự cần cấp quyền cho code classpath.
7. Kiểm thử bằng đúng JDK, build và launcher của môi trường triển khai.
8. Tạo công việc loại bỏ cờ sau khi dependency được nâng cấp.

## 18. Bài tập tự luyện

### Bài 1: Cờ nào có hiệu lực ở cả hai giai đoạn?

Một module cần truy cập kiểu public trong package JDK chưa export. Cờ nào có thể được dùng khi biên dịch và khi chạy?

**Đáp án:** `--add-exports`. Cần cấp quyền ở cả lệnh `javac` và lệnh `java` nếu muốn mã biên dịch và chạy với quyền đó. Ưu tiên API công khai thay thế nếu có.

### Bài 2: Cờ nào chỉ dành cho runtime?

Framework dùng reflection để đọc field private trong package chưa mở. Compiler không báo lỗi, nhưng runtime ném `InaccessibleObjectException`. Cờ nào có thể hỗ trợ chuyển tiếp?

**Đáp án:** `--add-opens` ở runtime, với đúng module nguồn/package và module gọi. Nếu package thuộc module ứng dụng, ưu tiên qualified `opens` trong descriptor.

### Bài 3: Vì sao --add-opens không sửa lỗi import?

Compiler báo package không visible, nhóm phát triển thêm `--add-opens` vào lệnh chạy nhưng lỗi compile vẫn còn. Vì sao?

**Đáp án:** `--add-opens` chỉ mở package cho deep reflection tại runtime. Nó không export package cho truy cập Java thông thường và không cấp quyền import khi biên dịch. Cần `exports` hoặc `--add-exports`, cùng readability phù hợp.

### Bài 4: Biên dịch thành công nhưng runtime IllegalAccessError

Một ứng dụng được biên dịch với `javac --add-exports ...` nhưng launcher không có cờ tương ứng. Điều gì có thể xảy ra?

**Đáp án:** Compiler cho phép truy cập nhưng runtime không có export bổ sung. Khi đường mã truy cập package được thực thi, JVM có thể ném `IllegalAccessError`. Cần đồng bộ quyền ở runtime hoặc chuyển sang API/module descriptor phù hợp.

### Bài 5: Có nên dùng ALL-UNNAMED?

Một framework named module cần reflection vào một package JDK. Có nên dùng `ALL-UNNAMED` không?

**Đáp án:** Không cần nếu đã biết tên module framework. Dùng tên module cụ thể để giới hạn quyền. `ALL-UNNAMED` dành cho code trên classpath và có phạm vi rộng hơn.

## Ghi nhớ

Compile-time và runtime là hai giai đoạn kiểm tra khác nhau. `--add-exports` có thể được dùng ở cả `javac` và `java`; nếu cần quyền truy cập trong cả hai giai đoạn, phải cấu hình cả hai. `--add-opens` chỉ có hiệu lực lúc runtime để cho phép deep reflection, không giúp compiler import package. `requires`, `exports` và `opens` trong module descriptor là cấu hình khai báo đi cùng module; cờ dòng lệnh là cầu nối có phạm vi hẹp. Trên JDK 17 trở lên, không dựa vào `--illegal-access`. Hãy xác định đúng loại quyền, đúng module đích và đúng giai đoạn trước khi thay đổi cấu hình.

## Tài liệu tham khảo

- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261).
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396).
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403).
- [Java Compiler — javac options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html).
- [Java Launcher — java options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
- [Java API — Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html).
- [Java API — AccessibleObject](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [JDK Tools — jdeps](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html).
