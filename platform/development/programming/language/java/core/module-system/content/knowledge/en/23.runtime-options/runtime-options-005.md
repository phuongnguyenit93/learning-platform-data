# --limit-modules giới hạn universe module

## 1. Ý nghĩa của --limit-modules

Khi khởi động ứng dụng modular, Java phải xác định những module nào có thể được nhìn thấy và đưa vào quá trình module resolution. Tập module mà module system có thể quan sát được gọi là **universe of observable modules**.

Tùy chọn runtime `--limit-modules` giới hạn universe này. Nó nhận danh sách tên module và thu hẹp tập module có thể được resolver xem xét xuống:

- Các module được liệt kê trực tiếp.
- Các module mà những module đó yêu cầu, theo chuỗi dependency `requires` (bao gồm các dependency gián tiếp).

Các module nằm ngoài tập giới hạn sẽ không còn observable trong lần chạy đó. Vì thế, nếu một root module hoặc dependency cần một module đã bị loại khỏi universe, quá trình resolution có thể thất bại với lỗi không tìm thấy module.

Điểm quan trọng: `--limit-modules` **giới hạn tập module có thể được nhìn thấy**, không phải danh sách module mà ứng dụng chắc chắn sẽ khởi tạo. Việc module nào thực sự được resolve còn phụ thuộc vào root modules, các directive `requires`, service binding và những tùy chọn launcher khác.

## 2. Universe module gồm những gì?

Thông thường, Java có thể quan sát các system modules của runtime image và các module ứng dụng tìm được trên module path. Khi dùng `--limit-modules`, universe được thu hẹp theo danh sách đã chọn cùng closure dependency của chúng.

Ví dụ có các module:

```text
com.acme.app
  requires com.acme.api
  requires java.logging

com.acme.api
  requires java.base

com.acme.provider.json
  requires com.acme.api
  provides com.acme.spi.Formatter with ...
```

Nếu giới hạn bằng:

```bash
--limit-modules com.acme.app
```

thì universe sẽ bao gồm `com.acme.app` và các module cần thiết theo dependency `requires` của nó, chẳng hạn `com.acme.api`, `java.logging` và `java.base`.

Module `com.acme.provider.json` không tự động thuộc closure chỉ vì nó khai báo `provides` cho một service. Nếu ứng dụng cần provider này thông qua service binding, phải bảo đảm provider vẫn nằm trong universe có thể quan sát. Có thể thêm nó vào danh sách:

```bash
--limit-modules com.acme.app,com.acme.provider.json
```

Việc giới hạn module không thay đổi nội dung JAR, không sửa `module-info.java` và không xóa module khỏi thư mục module path. Nó chỉ ảnh hưởng đến universe module trong lần chạy được cấu hình.

## 3. Cú pháp trên Java launcher

Cú pháp:

```bash
java --limit-modules module-name[,module-name...] ...
```

Ví dụ:

```bash
java --limit-modules java.base,java.logging \
  -m com.acme.app/com.acme.app.Main
```

Trong ứng dụng modular thực tế, cần bảo đảm root module và mọi dependency cần thiết đều nằm trong tập observable. Nếu `com.acme.app` cần `com.acme.api`, nhưng danh sách giới hạn không chứa app hoặc một module có dependency closure dẫn tới app, module app có thể không còn observable.

Một ví dụ đầy đủ với module path:

```bash
java --module-path mods \
  --limit-modules com.acme.app \
  -m com.acme.app/com.acme.app.Main
```

Ở đây:

- `--module-path mods` chỉ ra nơi tìm các application modules.
- `--limit-modules com.acme.app` giới hạn universe theo app và dependency closure của nó.
- `-m com.acme.app/com.acme.app.Main` chọn module và main class để chạy.

Nếu ứng dụng dùng provider chỉ được tìm thấy qua SPI, hãy cân nhắc đưa provider module vào danh sách giới hạn:

```bash
java --module-path mods \
  --limit-modules com.acme.app,com.acme.provider.json \
  -m com.acme.app/com.acme.app.Main
```

Tên module phải là tên module thực tế, không phải tên package hoặc tên class. Có thể kiểm tra tên module trong JAR bằng `jar --describe-module`.

## 4. Phân biệt --limit-modules với --add-modules

Hai tùy chọn có mục đích khác nhau:

| Tùy chọn | Vai trò |
|---|---|
| `--limit-modules` | Giới hạn universe module có thể quan sát và resolve |
| `--add-modules` | Thêm module được chỉ định vào tập root modules cần resolve |
| `--module-path` | Chỉ ra nơi tìm application modules |
| `--show-module-resolution` | In thông tin các module được resolve khi khởi chạy |

Ví dụ:

```bash
java --module-path mods \
  --add-modules java.sql \
  -m com.acme.app/com.acme.app.Main
```

`--add-modules java.sql` yêu cầu thêm `java.sql` làm root module. Nó không giới hạn universe các module có thể quan sát.

Ngược lại:

```bash
java --module-path mods \
  --limit-modules com.acme.app,java.sql \
  -m com.acme.app/com.acme.app.Main
```

`--limit-modules` chỉ thu hẹp universe. Nó không có nghĩa tất cả module trong danh sách đều tự động trở thành root module. Root ứng dụng vẫn được chọn bằng `-m`, `--module` hoặc cơ chế khởi chạy tương ứng.

Có thể kết hợp cả hai:

```bash
java --module-path mods \
  --limit-modules com.acme.app,java.sql \
  --add-modules java.sql \
  -m com.acme.app/com.acme.app.Main
```

Trong ví dụ này, `java.sql` vừa nằm trong universe được phép quan sát, vừa được thêm làm root module. Khi kết hợp, mọi module được yêu cầu làm root phải nằm trong universe giới hạn.

## 5. Tác động đến module resolution

Module resolution bắt đầu từ root modules và lần theo các dependency `requires`. `--limit-modules` thay đổi tập module đầu vào mà resolver có thể xem xét.

Giả sử ứng dụng có graph:

```text
com.acme.app
   |
   +-- requires com.acme.api
   |       |
   |       +-- requires java.base
   |
   +-- requires java.logging
```

Nếu universe chứa `com.acme.app`, các dependency cần thiết của nó cũng nằm trong closure và resolver có thể tìm chúng, miễn là các module tương ứng có sẵn trong các nguồn tìm kiếm hợp lệ.

Nếu `com.acme.api` không thể được tìm thấy trong universe hoặc trên các nguồn module hợp lệ, resolution không thể hoàn thành. Thông báo lỗi thường cho biết module nào đang bị thiếu; cần kiểm tra cả tên module lẫn danh sách giới hạn.

`--limit-modules` không tự sửa dependency thiếu, không biến `requires` thành optional và không export package. Nó chỉ quyết định module nào có thể được nhìn thấy trong quá trình resolution.

## 6. Tác động đến ServiceLoader và provider module

Trong kiến trúc SPI, consumer thường khai báo:

```java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
```

Provider khai báo:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

Khi dùng service binding, module system chỉ có thể xem xét các provider module mà nó quan sát được. Nếu `--limit-modules` loại provider khỏi universe, provider đó không thể được tự động tìm và đưa vào graph chỉ vì có directive `provides`.

Nếu ứng dụng cần provider cụ thể, hãy thêm provider module vào tập giới hạn:

```bash
java --module-path mods \
  --limit-modules com.acme.app,com.acme.provider.json \
  --show-module-resolution \
  -m com.acme.app/com.acme.app.Main
```

Sau khi khởi chạy, `ServiceLoader` chỉ có thể tìm các provider phù hợp trong layer mà nó được yêu cầu tìm kiếm. Vì vậy cần phân biệt:

1. Provider có nằm trong universe module được quan sát không?
2. Provider có được resolution/service binding đưa vào configuration và layer không?
3. Consumer có tìm provider trong đúng layer bằng `ServiceLoader` không?

Một provider nằm trên ổ đĩa nhưng bị giới hạn khỏi universe không thể được ServiceLoader tự tìm thấy từ layer đó.

## 7. Quan sát module universe và resolution

Có thể dùng `--list-modules` để xem danh sách module runtime quan sát được trong cấu hình launcher:

```bash
java --limit-modules java.base,java.logging --list-modules
```

Có thể dùng `--show-module-resolution` khi chạy ứng dụng để quan sát các module được resolve:

```bash
java --module-path mods \
  --limit-modules com.acme.app \
  --show-module-resolution \
  -m com.acme.app/com.acme.app.Main
```

Để kiểm tra descriptor của một module:

```bash
jar --describe-module --file mods/com.acme.api.jar
```

Nếu chưa biết tên module được suy ra từ JAR, lệnh này giúp xác nhận module name và các directive được khai báo. Với module đã có trong runtime image, có thể dùng:

```bash
java --describe-module java.logging
```

Khi debug, so sánh danh sách module có thể quan sát, module thực sự được resolve và các module được thêm làm root. Ba tập này có liên quan nhưng không đồng nghĩa.

## 8. Lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `FindException` hoặc thông báo không tìm thấy module | Module cần thiết bị loại khỏi universe, sai tên module hoặc không có trên module path |
| Root module không được tìm thấy | Danh sách `--limit-modules` không bao gồm root module và không có module được liệt kê nào yêu cầu nó |
| Ứng dụng thiếu provider SPI | Provider không nằm trong universe hoặc không được đưa vào layer |
| Thêm `--add-modules` nhưng vẫn báo module không tìm thấy | Module được thêm làm root nhưng lại không observable trong tập giới hạn |
| Ứng dụng chạy được trên cấu hình đầy đủ nhưng lỗi khi bật giới hạn | Có dependency gián tiếp hoặc provider mà danh sách giới hạn chưa tính tới |
| Danh sách module khác dự kiến | Đang so sánh universe observable với graph thực sự được resolve; hãy dùng cả `--list-modules` và `--show-module-resolution` |

Khi sửa, không nên thêm tất cả module một cách tùy tiện. Hãy xác định module bị thiếu, xem nó có phải dependency bắt buộc, provider SPI hay root module chủ động hay không, rồi cập nhật tập giới hạn theo nhu cầu thực tế.

## 9. Khi nào nên dùng --limit-modules?

Tùy chọn này hữu ích khi:

- Muốn kiểm thử ứng dụng với một universe module nhỏ và có kiểm soát.
- Muốn phát hiện dependency vô tình dựa vào module ngoài tập dự kiến.
- Muốn tái hiện môi trường runtime bị giới hạn để kiểm tra tính độc lập của ứng dụng.
- Muốn kiểm tra các module provider và dependency có được khai báo rõ ràng trong kiến trúc không.

Không nên xem `--limit-modules` là cách đóng gói runtime tối ưu hoặc thay thế kiểm tra bảo mật. Nó không xóa module khỏi JDK, không thay đổi bytecode, không giới hạn quyền truy cập file/network và không bảo đảm ứng dụng không dùng API ngoài danh sách theo mọi cơ chế khác.

Nếu mục tiêu là tạo runtime image nhỏ chứa đúng các module cần thiết để triển khai, hãy xem xét `jlink`. `--limit-modules` là tùy chọn giới hạn universe ở thời điểm chạy; `jlink` tạo runtime image tùy biến ở thời điểm build.

## 10. Checklist trước khi phát hành

- Xác nhận root module có nằm trong universe giới hạn.
- Xác nhận toàn bộ dependency `requires` cần thiết có thể được tìm thấy.
- Kiểm tra module provider cho SPI có cần được liệt kê riêng không.
- Nếu dùng `--add-modules`, bảo đảm các root được thêm cũng observable.
- Chạy với `--show-module-resolution` để kiểm tra graph thực tế.
- Chạy integration test với chính tập `--limit-modules` dự kiến trong production.
- Ghi lại danh sách giới hạn cùng cấu hình launch để việc triển khai có thể tái lập.

## Ghi nhớ

- `--limit-modules` thu hẹp universe observable xuống các module được liệt kê và dependency `requires` của chúng.
- Nó không tự thêm mọi module trong danh sách làm root; `--add-modules` đảm nhiệm việc thêm root modules.
- Module bị loại khỏi universe không thể được resolver sử dụng trong lần chạy đó.
- Provider SPI cũng phải nằm trong phạm vi module có thể quan sát nếu muốn service binding tìm thấy nó.
- Dùng `--list-modules` và `--show-module-resolution` để kiểm tra universe và graph.
- Muốn tạo runtime image nhỏ, cân nhắc `jlink`; `--limit-modules` chỉ giới hạn universe khi chạy.
