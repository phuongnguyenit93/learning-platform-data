# Đánh giá rủi ro khi dùng command line escape hatch

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao JPMS cung cấp các command-line escape hatch dù module system mặc định đóng gói package.
- Phân biệt chính xác tác động của `--add-exports`, `--add-opens`, `--add-reads` và `--patch-module`.
- Nhận diện khác biệt giữa quyền truy cập ở compile time và runtime.
- Đánh giá rủi ro tương thích, bảo trì và phạm vi ảnh hưởng của từng tùy chọn.
- Chọn cách sửa lâu dài thay vì giữ các cờ mở quyền truy cập vô thời hạn.
- Thiết lập, kiểm thử và quản lý escape hatch có phạm vi nhỏ, có chủ sở hữu và có thời hạn.

## 1. Vì sao cần command-line escape hatch?

Java Platform Module System (JPMS) đóng gói các package bên trong named module. Một module chỉ công khai package qua khai báo `exports`; nó có thể cho phép reflection sâu qua `opens`. Các module khác phải có quan hệ readability phù hợp trước khi dùng API của module đó.

Strong encapsulation bảo vệ ranh giới này. Khi một thư viện cũ cần truy cập package nội bộ của JDK, hoặc một framework cần reflection vào package chưa được mở, ứng dụng có thể gặp lỗi như:

- `package ... is not visible` khi biên dịch.
- `IllegalAccessError` khi truy cập type/member không được export.
- `InaccessibleObjectException` khi reflection cố truy cập sâu vào member bị đóng gói.
- `module ... does not read ...` khi thiếu quan hệ readability.

Các command-line escape hatch cho phép người vận hành nới một phần ranh giới module trong một lần chạy hoặc một cấu hình build cụ thể. Chúng hữu ích trong quá trình migration, tích hợp thư viện cũ, kiểm thử hoặc xử lý một giới hạn chưa thể sửa ngay.

Tuy nhiên, mỗi cờ thay đổi một quy tắc khác nhau. Dùng sai cờ có thể không giải quyết lỗi, trong khi vẫn làm cấu hình ứng dụng rộng và khó kiểm soát hơn.

## 2. Bốn loại quyền cần phân biệt

Trước khi chọn cờ, hãy xác định chính xác thao tác đang bị chặn:

1. **Readability**: module gọi có được phép đọc module chứa API hay không?
2. **Export**: package có công khai public type/member cho module gọi hay không?
3. **Open for reflection**: package có cho phép reflection sâu vào member không public hay không?
4. **Module content**: class/resource nào thực sự thuộc nội dung của module?

Các tùy chọn tương ứng:

| Tùy chọn | Thay đổi gì? | Phạm vi chính |
|---|---|---|
| `--add-reads` | Thêm quan hệ readability | Một module đọc được module khác |
| `--add-exports` | Export một package tới module đích | Truy cập public type trong package |
| `--add-opens` | Open một package cho reflection sâu | Runtime reflection |
| `--patch-module` | Bổ sung hoặc thay thế nội dung của module | Class/resource được nạp như thành phần của module |

Không có cờ nào là cách tổng quát để “tắt JPMS”. Cần xác định quy tắc đang thiếu rồi chọn thay đổi nhỏ nhất.

## 3. --add-exports: mở quyền truy cập public API của package

### 3.1. Ý nghĩa

Cú pháp:

~~~bash
--add-exports <source-module>/<package>=<target-module>
~~~

Tùy chọn này thêm một qualified export từ package của module nguồn đến module đích. Module đích có thể truy cập public type trong package đó theo quy tắc truy cập Java.

Ví dụ, một ứng dụng phụ thuộc vào API nội bộ `sun.nio.ch` của `java.base`:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out @sources.txt
~~~

Khi chạy ứng dụng tương ứng trên classpath:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out com.acme.Main
~~~

Hai lệnh minh họa hai thời điểm khác nhau:

- Cờ truyền cho `javac` cho phép compiler kiểm tra source có tham chiếu package đó.
- Cờ truyền cho `java` tạo quyền export tương ứng ở runtime.

Nếu ứng dụng là named module, hãy chỉ rõ module đích thay vì dùng `ALL-UNNAMED`:

~~~bash
java --add-exports java.base/sun.nio.ch=com.acme.app --module-path mods -m com.acme.app/com.acme.Main
~~~

### 3.2. Cờ này không làm gì?

`--add-exports` không mở package cho deep reflection. Nó cho phép truy cập public API của package theo quy tắc export; nó không tự cho phép framework truy cập private field hoặc gọi private method bằng reflection.

Nó cũng không biến API nội bộ thành API được JDK hỗ trợ ổn định. Package có thể thay đổi hoặc biến mất giữa các phiên bản JDK.

### 3.3. Rủi ro

- **Rủi ro tương thích cao** nếu package thuộc implementation nội bộ của JDK.
- **Rủi ro phạm vi** nếu dùng `ALL-UNNAMED`, vì mọi code trong unnamed module có thể nhận quyền export đó.
- **Rủi ro lệ thuộc** nếu nhiều thư viện cùng dựa vào package nội bộ và mỗi thư viện cần một cờ riêng.
- **Rủi ro triển khai** nếu chỉ thêm cờ ở compile time nhưng quên cấu hình runtime, hoặc ngược lại.

Dùng `--add-exports` khi vấn đề thực sự là code cần truy cập public type trong package chưa export. Nếu lỗi là deep reflection, hãy đánh giá `--add-opens` thay vì thêm export một cách máy móc.

## 4. --add-opens: cho phép deep reflection

### 4.1. Ý nghĩa

Cú pháp:

~~~bash
--add-opens <source-module>/<package>=<target-module>
~~~

`--add-opens` mở package ở runtime để module đích thực hiện reflective access sâu, bao gồm truy cập member không public khi các điều kiện reflection khác được đáp ứng.

Ví dụ, một framework cũ cần reflection vào private member thuộc package `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

Nếu chỉ một named module cần quyền đó:

~~~bash
java --add-opens java.base/java.lang=com.acme.framework --module-path mods -m com.acme.app/com.acme.Main
~~~

`ALL-UNNAMED` là target đặc biệt đại diện cho các unnamed module, thường là code chạy trên classpath. Nó không có nghĩa là mọi named module đều nhận quyền.

### 4.2. Khác với exports

| Tiêu chí | `--add-exports` | `--add-opens` |
|---|---|---|
| Mục đích | Truy cập public type trong package | Reflection sâu vào package |
| Compile time | Có thể dùng với javac | Không phải tùy chọn compile-time |
| Runtime | Có hiệu lực | Có hiệu lực |
| Private field/method | Không cấp quyền deep reflection | Cho phép deep reflection theo quy tắc reflection |
| Thay đổi API công khai | Tạo export cho target | Không tạo export cho truy cập Java thông thường |

Nếu một thư viện gọi `setAccessible(true)` hoặc `trySetAccessible()` trên member trong package bị đóng, lỗi thường liên quan đến openness. Thêm export có thể không giải quyết được lỗi đó.

### 4.3. Rủi ro

`--add-opens` có phạm vi mạnh hơn nhu cầu truy cập public API: framework có thể nhìn và thao tác với cấu trúc nội bộ của package. Điều này khiến ứng dụng dễ hỏng khi implementation thay đổi.

Các rủi ro thường gặp:

- Framework phụ thuộc vào tên field, cấu trúc object hoặc private method không phải hợp đồng ổn định.
- Nâng cấp JDK hoặc thư viện có thể làm reflection thất bại dù code ứng dụng không đổi.
- Dùng `ALL-UNNAMED` có thể mở package cho nhiều thư viện trên classpath ngoài dự kiến.
- Lỗi chỉ xuất hiện ở một số đường chạy ít được kiểm thử, chẳng hạn serialize, proxy, ORM hoặc dependency injection.

Chỉ mở đúng package cần thiết và chỉ cho đúng module đích. Không mở toàn bộ `java.base` hoặc toàn bộ package của một module chỉ để làm một lỗi reflection biến mất.

## 5. --add-reads: bổ sung quan hệ readability

### 5.1. Ý nghĩa

Cú pháp:

~~~bash
--add-reads <source-module>=<target-module>
~~~

Tùy chọn này thêm một cạnh readability: module nguồn được phép đọc module đích. Nó không export package và cũng không open package.

Ví dụ, named module `com.acme.app` cần đọc code ở unnamed module:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED --module-path mods -cp legacy-lib.jar -m com.acme.app/com.acme.Main
~~~

Một tình huống khác là module nguồn cần đọc module đích trong một cấu hình đặc biệt nhưng descriptor hiện tại chưa khai báo `requires` tương ứng.

### 5.2. Readability không đồng nghĩa với accessibility

Một module đọc được module khác chưa chắc đã truy cập được mọi package của module đó.

Để code sử dụng một public type, thông thường cần đồng thời:

- Module gọi có readability tới module chứa type.
- Package chứa type được export tới module gọi.
- Type/member đáp ứng quy tắc truy cập Java.

Nếu package chưa export, `--add-reads` không thay thế `--add-exports`. Nếu framework cần deep reflection, `--add-reads` cũng không thay thế `--add-opens`.

### 5.3. Rủi ro

- Làm đồ thị module phụ thuộc vào cấu hình triển khai thay vì descriptor.
- Che giấu một dependency chưa được khai báo trong `module-info.java`.
- Khi chuyển môi trường hoặc chạy test bằng cấu hình khác, cạnh readability có thể bị thiếu.
- Tạo cảm giác rằng module đã có hợp đồng dependency rõ ràng, trong khi thực tế chỉ được nối bằng cờ runtime.

Nếu dependency là quan hệ ổn định của module, hãy cân nhắc khai báo `requires` trong `module-info.java`. Dùng `--add-reads` cho trường hợp tích hợp tạm thời hoặc khi không thể sửa descriptor ngay.

## 6. --patch-module: thay đổi nội dung module

### 6.1. Ý nghĩa

Cú pháp:

~~~bash
--patch-module <module>=<path>
~~~

`--patch-module` chỉ định các class/resource bổ sung hoặc thay thế được nạp như một phần nội dung của module đã chọn. Nó thường được dùng trong kiểm thử, xây dựng patch đặc biệt hoặc các tình huống migration có kiểm soát.

Ví dụ, ứng dụng đã có module `com.acme.app` trong thư mục `mods`. Một thư mục patch chứa class đã biên dịch:

~~~bash
java --patch-module com.acme.app=patch-out --module-path mods -m com.acme.app/com.acme.Main
~~~

Có thể dùng `javac` để biên dịch source patch theo ngữ cảnh của module:

~~~bash
javac --module-path mods --patch-module com.acme.app=src/patch -d patch-out @patch-sources.txt
~~~

Trong các lệnh này:

- `com.acme.app` là module được patch.
- `patch-out` là nội dung đã biên dịch sẽ được nạp cùng module ở runtime.
- `src/patch` là source path của các class muốn biên dịch như một phần của module đó.

### 6.2. Patch không phải export hoặc open

`--patch-module` thay đổi tập class/resource thuộc module. Nó không phải cách khai báo package công khai cho module khác.

Nếu mục tiêu là cho module khác truy cập public type, hãy xem xét export. Nếu mục tiêu là reflection sâu, hãy xem xét opens. Nếu mục tiêu là thêm quan hệ đọc, hãy xem xét readability.

### 6.3. Rủi ro

- Có thể thay thế class đang được module sử dụng, khiến hành vi khác với artifact đã phát hành.
- Nội dung patch có thể không đồng bộ với phiên bản module gốc.
- Khó tái hiện lỗi nếu patch path khác nhau giữa môi trường developer, test và production.
- Có thể làm hỏng giả định về tính toàn vẹn của module hoặc tạo ra một runtime không tương ứng với artifact được kiểm thử/phê duyệt.
- Khi patch module của JDK, rủi ro tương thích và hỗ trợ tăng đáng kể.

Hãy ưu tiên dùng patch trong test hoặc công cụ phát triển. Nếu cần giữ patch ở production, cần quản lý nó như một phần của artifact và quy trình phát hành, có version, checksum, người sở hữu và kiểm thử tương thích.

## 7. Còn --illegal-access thì sao?

Trong các phiên bản Java đầu của JPMS, `--illegal-access` từng hỗ trợ migration bằng cách nới quyền truy cập phản chiếu tới một số package nội bộ của JDK.

Trạng thái quan trọng:

- JDK 9 đến JDK 15 có giai đoạn migration với các mức cảnh báo/cho phép khác nhau.
- JDK 16 chuyển sang strong encapsulation mặc định nghiêm ngặt hơn.
- Từ JDK 17, `--illegal-access` không còn là cách khôi phục hành vi truy cập rộng trước đây. Cờ này không thay thế các tùy chọn có phạm vi rõ ràng như `--add-opens` hoặc `--add-exports`.

Không nên thêm `--illegal-access=permit` vào script hiện đại với kỳ vọng giải quyết lỗi module. Hãy xác định package, module nguồn, module đích và loại truy cập thực sự cần thiết.

## 8. Đánh giá rủi ro theo tình huống

| Nhu cầu thực tế | Cờ có thể phù hợp | Rủi ro chính |
|---|---|---|
| Truy cập public type trong package chưa export | `--add-exports` | Phụ thuộc vào package không được công khai |
| Framework cần reflection sâu vào private member | `--add-opens` | Phụ thuộc vào implementation nội bộ |
| Module cần đọc module khác nhưng chưa có readability edge | `--add-reads` | Dependency bị ẩn trong cấu hình |
| Thay/bổ sung class hoặc resource của module | `--patch-module` | Runtime khác artifact gốc |
| Muốn mọi package đều truy cập được | Không có cờ tổng quát an toàn | Phạm vi vượt quá nhu cầu; cần xem lại thiết kế |

Một đánh giá có trách nhiệm cần trả lời ít nhất năm câu hỏi:

1. **Ai cần quyền?** Tên module cụ thể nào đang thực hiện truy cập?
2. **Cần quyền gì?** Readability, public access, deep reflection hay thay đổi nội dung?
3. **Cần tới đâu?** Một package, một module đích hay tất cả unnamed modules?
4. **Tồn tại bao lâu?** Chỉ một test, một phiên bản thư viện hay toàn bộ vòng đời ứng dụng?
5. **Có lối thoát không?** Có thể thay API, nâng cấp thư viện hoặc sửa descriptor không?

## 9. Quy trình quyết định trước khi thêm cờ

### Bước 1: Xác định lỗi gốc

Đọc đầy đủ exception và xác định:

- Module nguồn.
- Package bị chặn.
- Module đích.
- Thời điểm lỗi: compile time, class loading, ordinary access hay reflection.

Không chọn cờ chỉ dựa trên từ khóa `module` hoặc `access` trong thông báo lỗi.

### Bước 2: Xác nhận dependency đang gây ra truy cập

Tìm thư viện hoặc code thực hiện truy cập. Với thư viện bên thứ ba, kiểm tra phiên bản hỗ trợ JDK hiện tại và ghi nhận issue/documentation của nhà cung cấp.

Dùng công cụ dependency analysis khi phù hợp:

~~~bash
jdeps --jdk-internals application.jar
~~~

Lệnh này giúp phát hiện tham chiếu tới JDK internal APIs trong bytecode được phân tích. Kết quả là đầu mối điều tra; nó không tự chứng minh mọi đường chạy đều lỗi hoặc xác định toàn bộ reflection động.

Có thể kiểm tra module descriptor và dependency bằng:

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

### Bước 3: Chọn thay đổi nhỏ nhất

- Chỉ thiếu readability: xem xét `--add-reads`.
- Cần public type trong package chưa export: xem xét `--add-exports`.
- Cần reflection sâu ở runtime: xem xét `--add-opens`.
- Cần thay đổi class/resource thuộc module: xem xét `--patch-module` và xác định lý do patch thực sự cần thiết.

Không thêm nhiều cờ cùng lúc để “thử cho chạy”. Thay từng cờ, chạy lại test liên quan và ghi nhận cờ nào thực sự giải quyết lỗi.

### Bước 4: Giới hạn target

Ưu tiên module đích cụ thể:

~~~bash
java --add-opens java.base/java.lang=com.acme.framework --module-path mods -m com.acme.app/com.acme.Main
~~~

Chỉ dùng `ALL-UNNAMED` khi code cần quyền thực sự chạy trong unnamed module, chẳng hạn thư viện trên classpath. Đừng dùng nó làm giá trị mặc định cho mọi tình huống.

### Bước 5: Đặt thời hạn và kế hoạch gỡ bỏ

Mỗi escape hatch cần có:

- Lý do kỹ thuật và exception gốc.
- Module/package nguồn và module đích.
- Nơi cấu hình cờ: test task, application launcher, container hay service script.
- Phiên bản JDK và thư viện đã kiểm thử.
- Người sở hữu việc loại bỏ cờ.
- Điều kiện hoặc phiên bản mục tiêu để gỡ bỏ.

Nếu không có chủ sở hữu và điều kiện kết thúc, cờ tạm thời rất dễ trở thành một phần cấu hình vĩnh viễn.

## 10. Rủi ro khi đặt cờ ở sai nơi

Một cờ có thể được thêm ở nhiều lớp cấu hình:

- Lệnh chạy local.
- Test JVM của Gradle/Maven.
- Application plugin hoặc script khởi động.
- Docker image, service unit hoặc startup script.
- Biến môi trường ảnh hưởng tới nhiều JVM process.

Cùng một ứng dụng có thể chạy được trong local nhưng lỗi trong production vì cờ chỉ tồn tại ở một môi trường. Ngược lại, cờ đặt ở biến môi trường toàn cục có thể âm thầm mở quyền cho những JVM khác không liên quan.

Hãy đặt cờ ở lớp gần nhất với consumer cần quyền. Ví dụ, nếu chỉ test một framework cũ cần reflection, hãy giới hạn cờ trong test JVM. Chỉ đưa vào launcher production khi ứng dụng thực sự cần và đã kiểm thử cấu hình đó.

Không để nhiều nguồn cấu hình cùng khai báo các cờ khác nhau mà không có một nơi quản lý canonical. Khi điều tra runtime, cần có khả năng nhìn thấy chính xác JVM arguments thực tế.

## 11. Giải pháp lâu dài thay cho escape hatch

Ưu tiên theo thứ tự:

1. **Dùng API công khai** của JDK hoặc thư viện thay vì internal API.
2. **Nâng cấp thư viện** lên phiên bản hỗ trợ strong encapsulation và JDK mục tiêu.
3. **Thay cách tích hợp** bằng SPI, service provider, callback hoặc extension point được tài liệu hóa.
4. **Sửa module descriptor** của module do nhóm sở hữu bằng `exports`, qualified exports, `opens` hoặc `requires` phù hợp.
5. **Giảm phụ thuộc reflection** vào private implementation; dùng API được thiết kế để mở rộng.
6. **Giữ escape hatch có giới hạn** nếu chưa thể thay thế ngay, đồng thời tạo kế hoạch gỡ bỏ.

Nếu module của chính ứng dụng cần cho một framework truy cập reflection, một qualified `opens` trong descriptor có thể diễn đạt hợp đồng rõ hơn một cờ launcher áp dụng ở mọi môi trường. Tuy nhiên, chỉ mở package thực sự cần thiết và đúng module đích.

Không nên biến JDK internal API thành một dependency được hỗ trợ nội bộ chỉ vì `--add-exports` làm build chạy được. Escape hatch không thay đổi cam kết tương thích của nhà cung cấp API.

## 12. Checklist review một escape hatch

Trước khi merge hoặc phát hành cấu hình có escape hatch, hãy xác nhận:

- [ ] Đã lưu exception hoặc bằng chứng kỹ thuật ban đầu.
- [ ] Đã xác định đúng module nguồn, package và module đích.
- [ ] Đã chọn đúng loại quyền: reads, exports, opens hoặc patch.
- [ ] Đã dùng target hẹp nhất có thể; không dùng `ALL-UNNAMED` nếu không cần.
- [ ] Đã đặt cờ ở đúng JVM/build task.
- [ ] Đã kiểm thử trên JDK và thư viện mục tiêu.
- [ ] Đã kiểm tra các đường chạy reflection/class loading liên quan.
- [ ] Đã ghi chủ sở hữu và điều kiện gỡ bỏ.
- [ ] Đã có issue hoặc công việc migration cho giải pháp lâu dài.

## Kết luận

Command-line escape hatch là công cụ migration và tích hợp có kiểm soát. `--add-reads` thay đổi readability; `--add-exports` cấp quyền truy cập public type trong package; `--add-opens` cho phép deep reflection; `--patch-module` thay đổi nội dung được nạp như một phần của module. Mỗi cờ giải quyết một loại ranh giới khác nhau và tạo ra một dạng rủi ro riêng.

Hãy coi mỗi escape hatch là một khoản nợ tương thích có chủ sở hữu: **phạm vi nhỏ, target cụ thể, vị trí cấu hình rõ ràng, kiểm thử đúng môi trường và có điều kiện gỡ bỏ**. Khi có thể, hãy thay nó bằng API công khai hoặc hợp đồng module được khai báo rõ ràng.
